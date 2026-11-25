import micropyxel as pyxel

from cb_config import ASSET_BANK, COLKEY, SCREEN_W


COL_WHITE = 7
COL_RED = 8
COL_GREEN = 11
COL_YELLOW = 10
COL_DIM = 13


def blt_sprite(frame):
    u, v, w, h, x, y, _ms = frame
    pyxel.blt(x, y, ASSET_BANK, u, v, w, h, COLKEY)


def blt_region(region, x, y):
    u, v, w, h = region
    pyxel.blt(x, y, ASSET_BANK, u, v, w, h, COLKEY)


def text_width(text):
    return len(str(text)) * 4


def text_center(y, text, color):
    text = str(text)
    x = (SCREEN_W - text_width(text)) // 2
    if x < 0:
        x = 0
    pyxel.text(x, y, text, color)


def dots(y, color, tick, count=3):
    lit = (tick // 10) % (count + 1)
    start_x = (SCREEN_W - (count * 3 - 1)) // 2
    for i in range(count):
        col = color if i < lit else COL_DIM
        pyxel.pset(start_x + i * 3, y, col)
        pyxel.pset(start_x + i * 3 + 1, y, col)
