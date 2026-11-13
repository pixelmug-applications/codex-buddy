import { BubbleBot, InlineKeyboard, isNeedBindDeviceError } from "@jeejio-bubble/bot/sdk";
import PixelMugS1 from "@jeejio-bubble/bot/devices/pixelmug-s1";

const token = requiredEnv("BOT_TOKEN");
const apiBaseUrl = process.env.BOT_API_BASE_URL;
const mpsID = requiredEnv("STUDIO_MPS_ID");
const mpsVersion = requiredEnv("STUDIO_MPS_VERSION");

const mpsLaunchConfig = {
  id: mpsID, 
  version: mpsVersion,
};

const EMOJI = {
  bot: "\u{1F916}",
  sparkle: "\u{2728}",
  tools: "\u{1F6E0}\u{FE0F}",
  coffee: "\u{2615}",
  rocket: "\u{1F680}",
  warning: "\u{26A0}\u{FE0F}",
  repeat: "\u{1F501}",
  timer: "\u{23F3}",
};

const messages = {
  "zh-CN": {
    bindContent: "绑定 PixelMug 后即可使用 Codex Buddy。",
    bindButton: "绑定 PixelMug",
    addedIntro: "你好，我是 Codex Buddy 应用智能体。我的主要功能是把你的 PixelMug 变成 Codex 状态伙伴，显示等待、工作、编辑、需要批准、完成或失败等状态。在使用之前，请先绑定你的 PixelMug。",
  },
  "en-US": {
    bindContent: "Bind a PixelMug to use Codex Buddy.",
    bindButton: "Bind PixelMug",
    addedIntro: "Hello, I am the Codex Buddy app agent. I turn your PixelMug into a Codex status companion that shows states such as waiting, working, editing, approval needed, done, or failed. Before you start, please bind your PixelMug.",
  },
};

const CALLBACK_OPEN_ON_PIXELMUG = "codex-buddy:open-on-pixelmug";
const READY_EVENTS = new Set(["MPS_IS_RUNNING"]);
const FAILED_EVENTS = new Set(["INSTALL_FAIL", "RUNNING_FAIL"]);
const MPY_VM_ERROR_EVENT = "mpyVmError";
const MPY_VM_STATE_EVENT = "mpyVmEvent";
const RUNNING_FAIL_MESSAGE = "Install success. App internal error";
const MPS_OPEN_TIMEOUT_MS = Number(process.env.MPS_OPEN_TIMEOUT_MS || 45000);

const pendingLaunches = new Map();
const lastMpsEventByDevice = new Map();
const lastMpsErrorByDevice = new Map();

const pixelMug = new PixelMugS1();
const bot = new BubbleBot(token, {
  apiBaseUrl,
  webAppDeviceAccess: "none",
});

bot.registerDevices([pixelMug]);

bot.on("error", async (ctx) => {
  console.error("[codex-buddy-bot]", ctx.error || ctx);
});

bot.on("contact_added", async (ctx) => {
  await sendAddedIntro(ctx);
});

bot.on("joined_group", async (ctx) => {
  await sendAddedIntro(ctx, { mentionOnly: false });
});

bot.on("message", async (ctx) => {
  const command = extractCommand(ctx.message?.content || ctx.message?.text || "");

  if (command === "/bindPixelMug") {
    await sendBindDevice(ctx);
    return;
  }

  if (command === "/startBuddy") {
    const keyboard = new InlineKeyboard().text("Open on PixelMug", CALLBACK_OPEN_ON_PIXELMUG);
    await ctx.sendKeyboard(startMarkdown(), keyboard, {
      mentionOnly: ctx.chat?.type === "group" ? true : undefined,
    });
    return;
  }

  await ctx.sendText("Commands: /bindPixelMug, /startBuddy");
});

bot.on("callback", async (ctx) => {
  const value = extractCallbackValue(ctx.callback?.value);
  if (value !== CALLBACK_OPEN_ON_PIXELMUG) return;

  await openCodexBuddyOnPixelMug(ctx);
});

bot.on("device_notify", async (ctx) => {
  const events = pixelMug.parseNotify(ctx.tal?.notify || []);
  const key = deviceKeyFromNotify(ctx);

  for (const event of events) {
    if (event.name === MPY_VM_ERROR_EVENT) {
      const installError = parseMpsInstallError(event);
      if (key) lastMpsErrorByDevice.set(key, installError);

      const pending = key ? pendingLaunches.get(key) : firstPendingLaunch();
      if (!pending) continue;

      finishPendingLaunch(pending);
      await pending.ctx.sendText(formatMpsInstallError(installError));
      continue;
    }

    if (event.name !== MPY_VM_STATE_EVENT) continue;

    const value = String(event.params?.value || "");
    if (!value) continue;
    if (key) lastMpsEventByDevice.set(key, value);

    const pending = key ? pendingLaunches.get(key) : firstPendingLaunch();
    if (!pending) continue;

    if (READY_EVENTS.has(value)) {
      finishPendingLaunch(pending);
      await pending.ctx.sendText(`Script is running. Enjoy ${EMOJI.rocket}`);
      continue;
    }

    if (FAILED_EVENTS.has(value)) {
      finishPendingLaunch(pending);
      await pending.ctx.sendText(launchMessageForFailedEvent(value, key));
    }
  }
});

await bot.setCommands([
  {
    command: "bindPixelMug",
    description: "Bind PixelMug",
  },
  {
    command: "startBuddy",
    description: "Open Codex Buddy",
  },
]);

await bot.start();

console.log("mps-codex-buddy bot is running.");
console.log(`MPS launch config: ${mpsLaunchConfig.id}@${mpsLaunchConfig.version}`);

async function openCodexBuddyOnPixelMug(ctx) {
  await ctx.sendText(`Opening Codex Buddy on your PixelMug... ${EMOJI.sparkle}`);

  try {
    const responseCtx = await bot.callDevice(
      ctx.chat,
      pixelMug,
      pixelMug.rpc.talMpyExecOneScript(mpsLaunchConfig),
    );
    const code = mpyExecReturnCode(responseCtx.tal?.result);
    const key = deviceKeyFromResponse(responseCtx);

    if (code === 264) {
      await ctx.sendText(`Already running on your Mug. Enjoy ${EMOJI.coffee}`);
      return;
    }

    if (code === 260) {
      await ctx.sendText(`Script is already installed on your Mug ${EMOJI.sparkle}`);
    } else if (code === 261 || code === 262) {
      await ctx.sendText(`Installing Script on your Mug... ${EMOJI.tools}`);
    } else if (code === 263 || code === 265) {
      await ctx.sendText(`Switching Script on your Mug... ${EMOJI.repeat}`);
    } else {
      await ctx.sendText(`Could not open Codex Buddy on your Mug. Device returned code ${code || "unknown"}. ${EMOJI.warning}`);
      return;
    }

    waitForMpsRunning(ctx, key);
  } catch (error) {
    if (isNeedBindDeviceError(error)) {
      await ctx.sendBindDevice({
        content: "Bind a PixelMug before opening Codex Buddy.",
        actionButtonTitle: "Bind PixelMug",
      });
      return;
    }

    await ctx.sendText(`Could not open Codex Buddy on your Mug: ${errorMessage(error)} ${EMOJI.warning}`);
    throw error;
  }
}

function waitForMpsRunning(ctx, deviceKey) {
  const key = deviceKey || chatKey(ctx.chat);
  const lastEvent = lastMpsEventByDevice.get(key);

  if (lastEvent && READY_EVENTS.has(lastEvent)) {
    void ctx.sendText(`Script is running. Enjoy ${EMOJI.rocket}`);
    return;
  }

  if (lastEvent && FAILED_EVENTS.has(lastEvent)) {
    void ctx.sendText(launchMessageForFailedEvent(lastEvent, key));
    return;
  }

  clearPendingLaunch(key);

  const pending = {
    key,
    ctx,
    phases: new Set(),
    timer: setTimeout(async () => {
      pendingLaunches.delete(key);
      await ctx.sendText(`Still waiting for Codex Buddy to report ready on your Mug... ${EMOJI.timer}`);
    }, MPS_OPEN_TIMEOUT_MS),
  };
  if (typeof pending.timer.unref === "function") pending.timer.unref();
  pendingLaunches.set(key, pending);
}


function launchMessageForFailedEvent(value, key) {
  if (value === "RUNNING_FAIL") return RUNNING_FAIL_MESSAGE;

  const installError = key ? lastMpsErrorByDevice.get(key) : undefined;
  if (installError) return formatMpsInstallError(installError);

  return `Could not open Codex Buddy on your Mug. ${EMOJI.warning}`;
}

function parseMpsInstallError(event) {
  const rawValue = String(event.params?.value || "");
  return {
    code: parseInstallErrorCode(rawValue) || "unknown",
  };
}

function formatMpsInstallError(error) {
  return `install error: code ${error.code}`;
}

function parseInstallErrorCode(value) {
  const match = value.match(/INSTALL_ERROR:([-+]?\d+)/);
  return match?.[1] || "";
}
function firstPendingLaunch() {
  return pendingLaunches.values().next().value;
}

function finishPendingLaunch(pending) {
  clearTimeout(pending.timer);
  pendingLaunches.delete(pending.key);
}

function clearPendingLaunch(key) {
  const pending = pendingLaunches.get(key);
  if (!pending) return;
  clearTimeout(pending.timer);
  pendingLaunches.delete(key);
}

function startMarkdown() {
  return [
    `${EMOJI.bot} **Codex Buddy**`,
    "",
    "Codex Buddy turns your PixelMug into a tiny status companion for Codex.",
    "",
    "It receives local Codex activity through the companion bridge and shows useful states on the mug: waiting, working, editing, approval needed, done, or failed.",
    "",
    "Tap **Open on PixelMug** to install the app on your Mug.",
  ].join("\n");
}

function sendAddedIntro(ctx, options = {}) {
  const language = localeFromContext(ctx);
  return ctx.sendBindDevice({
    content: text(language, "addedIntro"),
    actionButtonTitle: text(language, "bindButton"),
    ...options,
  });
}

function sendBindDevice(ctx, language = localeFromContext(ctx)) {
  return ctx.sendBindDevice({
    content: text(language, "bindContent"),
    actionButtonTitle: text(language, "bindButton"),
  });
}

function localeFromContext(ctx) {
  const source = String(ctx.chat?.language || ctx.from?.language || process.env.APP_LOCALE || "").toLowerCase();
  return source.startsWith("zh") ? "zh-CN" : "en-US";
}

function text(language, key) {
  return messages[language]?.[key] || messages["en-US"][key] || key;
}

function mpyExecReturnCode(response) {
  if (typeof response === "number" || typeof response === "string") {
    const directCode = Number(response);
    if (Number.isFinite(directCode)) return directCode;
  }

  const data = response || {};
  const result = data.result;
  const value = typeof result === "object" && result !== null
    ? result.value ?? result.return
    : result ?? data.value ?? data.return;
  const code = Number(value);
  return Number.isFinite(code) ? code : Number(data.code);
}

function deviceKeyFromResponse(ctx) {
  return String(ctx.from?.id || ctx.webAppDeviceCall?.deviceId || ctx.tal?.response?.from || "");
}

function deviceKeyFromNotify(ctx) {
  return String(ctx.from?.id || "");
}

function chatKey(chat) {
  return `${chat?.type || "chat"}:${chat?.id || chat?.name || ""}`;
}

function extractCommand(text) {
  const match = String(text || "").trim().match(/\/[a-zA-Z0-9_-]+(?:@[a-zA-Z0-9_-]+)?/);
  if (!match) return "";
  return match[0].split("@")[0];
}

function extractCallbackValue(value) {
  if (typeof value === "string") return value;
  if (value?.value) return value.value;
  if (value?.data) return value.data;
  return "";
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error || "Unknown error");
}

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required environment variable: ${name}`);
  return value;
}
