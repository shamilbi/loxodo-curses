import threading
import time
from contextlib import contextmanager
from signal import SIGINT, pthread_kill


class StopThread(threading.Thread):
    'wait timeout ... raise SIGINT to stop App'

    def __init__(self, timeout: int, stop: threading.Event):
        if timeout <= 0:
            raise ValueError('timeout <= 0')

        self.timeout = timeout  # sec
        self.stop = stop

        self.lock = threading.RLock()
        self.t0 = 0.0
        self.parent = threading.get_ident()

        super().__init__()

    def reset(self):
        with self.lock:
            self.t0 = time.time()

    def suspend(self):
        with self.lock:
            self.t0 = -1

    def run(self):
        self.reset()
        t = self.timeout
        while True:
            if self.stop.wait(t):
                return
            with self.lock:
                if self.t0 < 0:
                    # wait indefinitely
                    t = self.timeout
                    continue
                dt = int(time.time() - self.t0)
                if dt >= self.timeout:
                    pthread_kill(self.parent, SIGINT)
                    break
            t = self.timeout - dt


class ClearTimer:
    'timer to clear clipboard'

    def __init__(self, interval: int | float, func):
        self.interval = interval
        self.func = func
        self.timer: threading.Timer | None = None

    def stop(self):
        t = self.timer
        if t and t.is_alive():
            t.cancel()
        self.timer = None

    def start(self):
        self.stop()
        self.timer = threading.Timer(self.interval, self.func)
        self.timer.start()

    @contextmanager
    def stop_start(self):
        self.stop()
        try:
            yield
        finally:
            self.start()
