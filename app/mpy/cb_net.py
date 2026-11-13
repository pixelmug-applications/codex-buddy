try:
    import usocket as socket
except ImportError:
    import socket

try:
    import network
except ImportError:
    network = None


def wifi_status_text():
    if network is None:
        return "network module unavailable"
    try:
        sta = network.WLAN(network.STA_IF)
        if not sta.active():
            return "wifi inactive"
        if not sta.isconnected():
            return "wifi not connected"
        return "wifi ip=%s" % (sta.ifconfig()[0],)
    except Exception as exc:
        return "wifi check failed: %s" % exc


def make_udp_socket(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except Exception:
        pass
    sock.bind(("0.0.0.0", port))
    sock.setblocking(False)
    return sock
