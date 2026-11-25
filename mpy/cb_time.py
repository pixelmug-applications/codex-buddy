import time


def now_ms():
    return time.ticks_ms()


def ticks_add(ms, delta):
    return time.ticks_add(ms, delta)


def ticks_diff(a, b):
    return time.ticks_diff(a, b)
