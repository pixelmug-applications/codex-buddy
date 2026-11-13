import micropyxel as pyxel
import time

from cb_anim import TimedAnimation
from cb_assets import ANIMS
from cb_draw import COL_DIM, COL_GREEN, COL_WHITE, COL_RED, blt_sprite, text_center
from cb_utils import clamp_percent


def anim_key(host_state):
    if host_state == "permission":
        return "permission"
    if host_state == "idle":
        return "idle"
    if host_state == "done":
        return "done"
    if host_state == "session" or host_state == "error":
        return "idle"
    return "working"


class FunctionScreen:
    def __init__(self):
        self.page = 0
        self.anim_name = ""
        self.anim = None

    def next_page(self):
        self.page = 1 - self.page

    def draw(self, ctx):
        pyxel.cls(0)
        if self.page == 1:
            self.draw_usage(ctx)
            return
        key = anim_key(ctx.host_state)
        if key != self.anim_name:
            self.anim_name = key
            self.anim = TimedAnimation(ANIMS[key])
        frame = self.anim.current()
        if frame:
            blt_sprite(frame)

    def draw_usage(self, ctx):
        five = clamp_percent(ctx.usage.get("quota_5h_remaining_percent"))
        seven = clamp_percent(ctx.usage.get("quota_7d_remaining_percent"))

        # A 32x16 display cannot show both windows and reset values at once.
        # On Plus, alternate between the 5-hour and weekly windows; on Pro,
        # the missing 5-hour window naturally falls back to the weekly view.
        if five is not None and seven is not None:
            show_five = ((ctx.frame // 90) % 2) == 0
        else:
            show_five = five is not None

        if show_five:
            percent = five
            reset = self._format_remaining(ctx.usage.get("quota_5h_resets_at"), "H", 3600)
            label = "5H"
        else:
            percent = seven
            reset = self._format_remaining(ctx.usage.get("quota_7d_resets_at"), "D", 86400)
            label = "7D"

        if percent is None:
            text_center(2, "USAGE:--", COL_WHITE)
            text_center(9, "WAITING", COL_DIM)
            return

        value_text = "%s:%s" % (label, "%d%%" % percent)
        reset_text = "RST %s" % reset
        color = COL_RED if percent <= 20 else COL_WHITE
        text_center(2, value_text, color)
        text_center(9, reset_text, COL_GREEN)

    @staticmethod
    def _format_remaining(timestamp, unit, unit_seconds):
        try:
            remaining = int(timestamp) - int(time.time())
            if remaining < 0:
                remaining = 0
            value = (remaining + unit_seconds - 1) // unit_seconds
            return "%d%s" % (value, unit)
        except Exception:
            return "--"
