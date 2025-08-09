
import shutil
from printer import perror
if shutil.which("npx") is None:
    perror("npx is not installed or not found in PATH")

import os
import psutil
import subprocess

from printer import monitor_stderr

class Gamepad_Viewer:

    def __init__(self):
        self.background_process = None

    def open_live_view(self):
        electron_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Electron-GamepadViewer'))
        cmd = ["npx", "electron", "."]
        try:
            self.background_process = subprocess.Popen(cmd, cwd=electron_dir, stderr=subprocess.PIPE)
            monitor_stderr(self.background_process, "ELECTRON")
        except Exception as e:
            perror(f"Failed to launch GamepadViewer: {e}")

    def close_live_view(self):
        if self.background_process:
            parent = psutil.Process(self.background_process.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
            print("GamepadViewer process terminated")
        else:
            print("No GamepadViewer process to terminate")
