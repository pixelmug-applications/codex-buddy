try:
    import ujson as json
except ImportError:
    import json

from cb_config import PAIR_FILE, PAIR_PORT, STATUS_PORT


def default_pairing():
    return {
        "paired": False,
        "bridge_id": "",
        "token": "",
        "device_id": "",
        "device_name": "PixelMug",
        "status_port": STATUS_PORT,
        "pair_port": PAIR_PORT,
    }


def load_pairing():
    try:
        with open(PAIR_FILE, "r") as fp:
            data = json.loads(fp.read() or "{}")
        if data.get("paired") and data.get("token"):
            data["status_port"] = data.get("status_port") or STATUS_PORT
            data["pair_port"] = data.get("pair_port") or PAIR_PORT
            return data
    except Exception:
        pass
    return default_pairing()


def save_pairing(data):
    with open(PAIR_FILE, "w") as fp:
        fp.write(json.dumps(data))
