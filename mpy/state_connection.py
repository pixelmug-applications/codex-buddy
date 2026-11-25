import micropyxel as pyxel

from cb_assets import CODEX_LOGO, CONNECT_OFF, CONNECT_OK, PIXELMUG_LOGO
from cb_config import FPS
from cb_draw import blt_region


class ConnectionScreen:
    def draw(self, ctx):
        pyxel.cls(0)
        if ctx.paired:
            blt_region(CODEX_LOGO, 2, 4)
            blt_region(PIXELMUG_LOGO, 20, 4)
            if ctx.connected:
                blt_region(CONNECT_OK, 14, 6)
            else:
                blt_region(CONNECT_OFF, 14, 5)
            return

        move_frames = 6
        pause_frames = FPS
        phase = ctx.frame % (move_frames * 2 + pause_frames)
        if phase < move_frames:
            x = 2 + (phase * 4 // (move_frames - 1))
        elif phase < move_frames * 2:
            x = 7 - ((phase - move_frames) * 5 // (move_frames - 1))
        else:
            x = 2
        blt_region(CODEX_LOGO, x, 4)
        blt_region(PIXELMUG_LOGO, 20, 4)
