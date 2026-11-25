try:
    import ujson as json
except ImportError:
    import json

try:
    import ubinascii as binascii
except ImportError:
    import binascii

try:
    import urandom as random
except ImportError:
    import random

try:
    from maopaoAuth import jeekey
except ImportError:
    jeekey = None

try:
    import machine
except ImportError:
    machine = None

from cb_time import now_ms


def short(value, limit):
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def clamp_percent(value):
    try:
        value = float(value)
    except Exception:
        return None
    if value < 0:
        value = 0
    if value > 100:
        value = 100
    return int(value + 0.5)


def json_bytes(obj):
    return json.dumps(obj).encode("utf-8")


def parse_json(data):
    try:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        value = json.loads(data)
    except Exception:
        return None
    if isinstance(value, dict):
        return value
    return None


def normalize_device_id(value):
    text = short(value, 64)
    if not text:
        return ""
    out = []
    for ch in text:
        if ("0" <= ch <= "9") or ("A" <= ch <= "Z") or ("a" <= ch <= "z") or ch in ("-", "_"):
            out.append(ch)
        elif ch == " ":
            out.append("-")
    return "".join(out)[:64]


def make_device_id():
    if jeekey is not None:
        try:
            sn = normalize_device_id(jeekey.get_sn())
            if sn:
                return sn
        except Exception:
            pass
        try:
            device_id = normalize_device_id(jeekey.get_device_id())
            if device_id:
                return device_id
        except Exception:
            pass

    suffix = ""
    try:
        if machine is not None:
            raw = machine.unique_id()
            suffix = binascii.hexlify(raw[-2:]).decode("ascii").upper()
    except Exception:
        suffix = ""
    if not suffix:
        suffix = "%04X" % (now_ms() & 0xFFFF)
    return "pixelmug-" + suffix


def make_pair_code():
    try:
        value = random.getrandbits(20)
    except Exception:
        value = now_ms() & 0xFFFFF
    return "%06d" % (value % 1000000)
