import shutil
import subprocess
import psutil
from printer import perror, monitor_stderr

if not shutil.which("npx"):
    perror("npx is not installed or not found in PATH")

class GamepadViewer:
    def __init__(self):
        self.process = None

    def start_mirroring(self):
        # Start Electron gamepad viewer in the background
        try:
            self.process = subprocess.Popen(["npx", "electron", "gamepad_viewer"], stderr=subprocess.PIPE)
            monitor_stderr(self.process, "GAMEPAD VIEWER")
            print("GAMEPAD VIEWER process launched")
        except Exception as e:
            perror(f"Failed to launch GAMEPAD VIEWER: {e}")

    def stop_mirroring(self):
        # Kill Electron process and its child processes
        if not self.process:
            print("No GAMEPAD VIEWER process to terminate")
            return

        try:
            parent = psutil.Process(self.process.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
            print("GAMEPAD VIEWER process terminated")
        except psutil.NoSuchProcess:
            print("GAMEPAD VIEWER process already dead")
        finally:
            self.process = None
