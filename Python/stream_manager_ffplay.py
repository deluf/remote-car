import shutil
import subprocess
from enum import Enum
from pathlib import Path
import psutil
from printer import perror, monitor_stderr

if shutil.which("ffplay") is None:
    perror("ffplay is not installed or not found in PATH")

# Stream parameters
ORIGINAL_STREAM_WIDTH = 320
ORIGINAL_STREAM_HEIGHT = 240
FRAMERATE = 30
UDP_PORT = 8001

# Device parameters
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900
FONT_BOLD = "/Users/fra/Library/Fonts/Mx437_IBM_VGA_8x16.ttf"
FONT_NORMAL = "/Users/fra/Library/Fonts/Mx437_IBM_DOS_ISO8.ttf"

SCALED_WIDTH = SCREEN_HEIGHT / ORIGINAL_STREAM_WIDTH * ORIGINAL_STREAM_HEIGHT

class LensFacing(Enum):
    FRONT = 0
    BACK = 1

INPUT_FLAGS = [
    "-loglevel", "error",
    "-fflags", "nobuffer",
    "-flags", "low_delay", 
    "-framedrop",
    "-f", "h264",
    "-framerate", f"{FRAMERATE}",
    "-an", # Disable the audio
    "-noborder",
    "-alwaysontop",
    "-left", f"{int((SCREEN_WIDTH - SCALED_WIDTH) // 2)}", # Center on screen
    "-top", "0",
    "-i", f"udp://0.0.0.0:{UDP_PORT}"
]

VIDEO_FILTERS = [
    "transpose=1", # 90 degree rotation clockwise
    f"scale={int(SCALED_WIDTH)}:{SCREEN_HEIGHT}", # Scale to fit screen height
    # Auto-updating camera source text
    f"drawtext=fontfile={FONT_BOLD}:"
    "textfile=/tmp/camera_source.ffplayvf:"
    "fontsize=h/25:"
    "fontcolor=white:"
    "bordercolor=black:"
    "borderw=1:"
    "x=(w-text_w)/2:"
    "y=20:"
    "reload=5:",
    # Auto-updating timestamp
    f"drawtext='fontfile={FONT_NORMAL}:"
    r"text=%{localtime\:%-d %b %Y %X}':"
    "fontsize=h/30:"
    "fontcolor=white:"
    "x=w-text_w-10:"
    "y=h-text_h-10"
]

CMD = ["ffplay"] + INPUT_FLAGS + ["-vf", ",".join(VIDEO_FILTERS)]

class StreamManagerFFplay:
    def __init__(self):
        self.process = None
        self.lens_facing = LensFacing.FRONT
        self.camera_source_file = Path("/tmp/camera_source.ffplayvf")
        self.camera_source_file.write_text(f"{self.lens_facing.name} CAMERA")

    def play(self):
        if self.process:
            print("Stream already launched")
            return
        try:
            self.process = subprocess.Popen(CMD, stderr=subprocess.PIPE, text=True)
            monitor_stderr(self.process, "FFPLAY")
        except Exception as e:
            perror(f"Failed to play the stream: {e}")

    def switch(self):
        self.lens_facing = LensFacing.FRONT if self.lens_facing == LensFacing.BACK else LensFacing.BACK
        self.camera_source_file.write_text(f"{self.lens_facing.name} CAMERA")

    def close(self):
        if not self.process:
            print("No stream process to terminate")
            return
        try:
            parent = psutil.Process(self.process.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
            print("Stream process terminated")
        except psutil.NoSuchProcess:
            print("Stream process already dead")
        finally:
            self.process = None
