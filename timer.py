#!/usr/bin/env python3

from threading import Timer
from typing import Callable

class RepeatingTimer:
    def __init__(self, interval: int = 1, callback: Callable = lambda: None, auto_start: bool = True):
        self._timer = None
        self.interval = interval
        self.callback = callback
        self.running: bool = False
        if auto_start:
            self.start()

    def _run(self):
        self.running = False
        self.start()
        self.callback()

    def start(self):
        if not self.running:
            self.running = True
            self._timer = Timer(self.interval, self._run)
            self._timer.start()

    def stop(self):
        self.running = False
        if self._timer:
            self._timer.cancel()
