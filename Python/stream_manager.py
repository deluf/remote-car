
import shutil
from printer import perror
if shutil.which("ffplay") is None:
    perror("ffplay is not installed or not found in PATH")

import subprocess
import psutil
from enum import Enum
from pathlib import Path
from printer import monitor_stderr

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

class LENS_FACING(Enum):
    FRONT = 0
    BACK = 1

# Possible unused flags:
#  -fast
#  -sync video

INPUT_FLAGS = [
    "-loglevel", "error",
    "-fflags", "nobuffer",
    "-flags", "low_delay", 
    "-framedrop",
    "-f", "h264",
    "-framerate", f"{FRAMERATE}",
    # Disable the audio (streamed separately)
    "-an", 
    "-noborder",
    "-alwaysontop",
    # Position the stream in the center of the screen
    "-left", f"{(SCREEN_WIDTH - SCALED_WIDTH)//2}",
    "-top", "0",
    "-i", f"udp://0.0.0.0:{UDP_PORT}"   
]

VIDEO_FILTERS = [
    # 90° rotation clockwise
    "transpose=1",

    # Scale the stream to fit the entire screen height
    f"scale={SCALED_WIDTH}:{SCREEN_HEIGHT}",

    # Auto-updating FRONT/BACK camera text
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
    r"text=%{localtime\:%-d %b %Y %X}':" # strftime style 
    "fontsize=h/30:"
    "fontcolor=white:"
    "x=w-text_w-10:"
    "y=h-text_h-10",
]

CMD = (
    ["ffplay"] + 
    INPUT_FLAGS + 
    ["-vf"] +
    [",".join(VIDEO_FILTERS)]
)

class Stream_Manager:

    def __init__(self):
        self.background_process = None
        self.lens_facing = LENS_FACING.FRONT

        # Initialize the files referenced in the video filters
        self.camera_source_file = Path("/tmp/camera_source.ffplayvf")
        self.camera_source_file.write_text(f"{self.lens_facing.name} CAMERA")

    def play(self):
        if self.background_process:
            print(f"Stream already launched")
            return
        try:
            self.background_process = subprocess.Popen(CMD, stderr=subprocess.PIPE, text=True)
            monitor_stderr(self.background_process, "FFPLAY")
        except Exception as e:
            perror(f"Failed to play the stream: {e}")

    def switch(self):
        self.lens_facing = LENS_FACING.FRONT if self.lens_facing == LENS_FACING.BACK else LENS_FACING.BACK
        self.camera_source_file.write_text(f"{self.lens_facing.name} CAMERA")

    def close(self):
        if self.background_process:
            parent = psutil.Process(self.background_process.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
            print(f"Stream process terminated")
        else:
            print(f"No stream process to terminate")
