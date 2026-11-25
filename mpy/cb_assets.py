import micropyxel as pyxel

from cb_config import ASSET_BANK, ASSET_PATH, INCLUDE_COLORS


def load_assets():
    pyxel.images(ASSET_BANK).load_from_png(0, 0, ASSET_PATH, INCLUDE_COLORS)


def sprite(x1, y1, x2, y2, dx, dy, ms):
    return (x1, y1, x2 - x1 + 1, y2 - y1 + 1, dx, dy, ms)


CODEX_LOGO = (3, 63, 11, 9)
PIXELMUG_LOGO = (21, 63, 9, 9)
CONNECT_OK = (15, 65, 5, 1)
CONNECT_OFF = (15, 59, 5, 5)

ANIMS = {
    "permission": (
        sprite(5, 97, 28, 111, 5, 1, 150),
        sprite(37, 97, 60, 111, 5, 1, 150),
    ),
    "idle": (
        sprite(6, 115, 21, 127, 6, 3, 800),
        sprite(37, 114, 56, 127, 5, 2, 800),
        sprite(70, 114, 91, 127, 6, 2, 800),
        sprite(101, 112, 127, 127, 5, 0, 800),
    ),
    "done": (
        sprite(6, 81, 30, 95, 6, 1, 2000),
        sprite(38, 81, 62, 95, 6, 1, 50),
        sprite(70, 81, 94, 95, 6, 1, 100),
    ),
    "working": (
        sprite(3, 129, 18, 143, 3, 1, 300),
        sprite(36, 129, 51, 143, 4, 1, 300),
        sprite(70, 129, 85, 143, 6, 1, 300),
        sprite(104, 129, 119, 143, 8, 1, 300),
        sprite(138, 129, 153, 143, 10, 1, 300),
        sprite(172, 129, 187, 143, 12, 1, 300),
        sprite(207, 129, 220, 143, 15, 1, 180),
        sprite(239, 129, 252, 143, 15, 1, 180),
        sprite(15, 145, 28, 159, 15, 1, 180),
        sprite(47, 145, 60, 159, 15, 1, 180),
        sprite(79, 145, 92, 159, 15, 1, 180),
        sprite(111, 145, 124, 159, 15, 1, 180),
        sprite(141, 145, 156, 159, 13, 1, 300),
        sprite(171, 145, 186, 159, 11, 1, 300),
        sprite(201, 145, 216, 159, 9, 1, 300),
        sprite(231, 145, 246, 159, 7, 1, 300),
        sprite(5, 161, 20, 175, 5, 1, 300),
        sprite(35, 161, 50, 175, 3, 1, 300),
        sprite(68, 161, 81, 175, 4, 1, 300),
        sprite(100, 161, 113, 175, 4, 1, 300),
        sprite(132, 161, 145, 175, 4, 1, 300),
        sprite(164, 161, 177, 175, 4, 1, 300),
        sprite(196, 161, 209, 175, 4, 1, 300),
        sprite(228, 161, 241, 175, 4, 1, 300),
    ),
}
