
import shutil
from printer import perror
if shutil.which("npx") is None:
    perror("npx is not installed or not found in PATH")

import psutil
import subprocess

from printer import monitor_stderr

class Gamepad_Viewer:

    def __init__(self):
        self.background_process = None

    def start_mirroring(self):
        cmd = ["npx", "electron", "gamepad_viewer"]
        try:
            self.background_process = subprocess.Popen(cmd, stderr=subprocess.PIPE)
            monitor_stderr(self.background_process, "GAMEPAD VIEWER")
            print("GAMEPAD VIEWER process launched")
        except Exception as e:
            perror(f"Failed to launch GAMEPAD VIEWER: {e}")

    def stop_mirroring(self):
        if self.background_process:
            parent = psutil.Process(self.background_process.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
            print("GAMEPAD VIEWER process terminated")
        else:
            print("No GAMEPAD VIEWER process to terminate")
