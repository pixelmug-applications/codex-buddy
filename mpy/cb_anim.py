from cb_time import now_ms, ticks_diff


class TimedAnimation:
    def __init__(self, frames):
        self.frames = frames
        self.index = 0
        self.deadline = 0

    def current(self):
        now = now_ms()
        if not self.frames:
            return None
        if not self.deadline:
            self.deadline = now + self.frames[self.index][6]
        while ticks_diff(now, self.deadline) >= 0:
            self.index = (self.index + 1) % len(self.frames)
            self.deadline += self.frames[self.index][6]
        return self.frames[self.index]
