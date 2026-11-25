import micropyxel as pyxel

from cb_draw import COL_GREEN, COL_RED, COL_WHITE, dots, text_center


class PairingScreen:
    def draw(self, ctx):
        pyxel.cls(0)
        phase = ctx.pair_view
        if phase == "verifying":
            text_center(2, "Paring", COL_WHITE)
            dots(12, COL_GREEN, ctx.frame)
        elif phase == "error":
            text_center(5, "Err", COL_RED)
        elif phase == "ok":
            text_center(5, "OK", COL_GREEN)
        elif phase == "timeout":
            text_center(5, "Timeout", COL_RED)
        else:
            text_center(2, ctx.pair_code or "------", COL_WHITE)
            dots(12, COL_RED, ctx.frame)
