
import subprocess
import psutil
from pathlib import Path

class Stream_Manager:

    def __init__(self):

        self.background_process = None

        # Possible unused flags:
        #  -fast
        #  -sync video

        self.INPUT_FLAGS = [
            "-fflags", "nobuffer",
            "-flags", "low_delay", 
            "-framedrop",
            "-f", "h264",
            "-framerate", "30",
            "-an", # Disable the audio (streamed separately)
            "-noborder",
            "-alwaysontop",
            "-left", f"{1440 - 675 - (1440-675)//2 - 1}",
            "-top", "0",
            "-window_title", "FRONT CAMERA FEED",
            "-i", "udp://0.0.0.0:8001"
        ]

        # Normal = /Users/fra/Library/Fonts/Mx437_IBM_DOS_ISO8.ttf
        # Bold = /Users/fra/Library/Fonts/Mx437_IBM_VGA_8x16.ttf

        self.VIDEO_FILTERS = [
            "scale=900:675",    # No matter what the stream resolution is, always display at 640x480
            "transpose=1",      # 90° rotation clockwise

            # FRONT CAMERA
            "drawtext=fontfile=/Users/fra/Library/Fonts/Mx437_IBM_VGA_8x16.ttf:"
            "text=FRONT CAMERA:"
            "fontsize=h/25:"
            "fontcolor=white:"
            "bordercolor=black:"
            "borderw=1:"
            "x=(w-text_w)/2:"
            "y=20",

            # Timestamp
            "drawtext='fontfile=/Users/fra/Library/Fonts/Mx437_IBM_DOS_ISO8.ttf:"
            r"text=%{localtime\:%-d %b %Y %X}':" # strftime style 
            "fontsize=h/30:"
            "fontcolor=white:"
            "x=w-text_w-10:"
            "y=h-text_h-10",
            
            # Example of dynamic text
            "drawtext=fontfile=/Users/fra/Library/Fonts/Mx437_IBM_DOS_ISO8.ttf:"
            "textfile=/tmp/bw.txt:"
            "fontsize=h/30:"
            "fontcolor=white:"
            "x=10:"
            "y=h-text_h-10:"
            "reload=15:"  # Reload every 15 frames
        ]
        
        self.CMD = (
            ["ffplay"] + 
            self.INPUT_FLAGS + 
            ["-vf"] +
            [",".join(self.VIDEO_FILTERS)]
        )
        
    def play_front_camera(self):
        
        # Ensure that the files referenced from the video filters exist
        bw_file = Path("/tmp/bw.txt")
        if not bw_file.exists():
            bw_file.write_text("468 Kbps")
    
        try:
            self.background_process = subprocess.Popen(self.CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Failed to launch ffplay: {e}")

    def close_front_camera(self):
        parent = psutil.Process(self.background_process.pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
        print("ffplay process terminated and its children terminated")
