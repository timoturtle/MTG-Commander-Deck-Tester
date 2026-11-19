"""Keep the computer awake while a test runs (macOS: caffeinate, Windows: SetThreadExecutionState)."""
import os
import subprocess
import sys


class KeepAwake:
    def __init__(self, log=print):
        self.log = log
        self.proc = None
        self.win = False

    def __enter__(self):
        try:
            if sys.platform == "darwin":
                # -i: no idle sleep, -s: no system sleep on power adapter, -w: end with this app
                self.proc = subprocess.Popen(["caffeinate", "-i", "-s", "-w", str(os.getpid())],
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif os.name == "nt":
                import ctypes
                ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
                self.win = True
        except Exception as e:
            self.log(f"Could not keep the computer awake: {e}")
        return self

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        if self.win:
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            except Exception:
                pass
        return False
