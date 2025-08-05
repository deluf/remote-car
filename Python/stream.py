
import subprocess
import sys
from pathlib import Path

def start_ffplay():
    # Ensure /tmp/bw.txt exists (create empty if not)
    bw_file = Path("/tmp/bw.txt")
    if not bw_file.exists():
        bw_file.write_text("468 Kbps")
        print(f"Created {bw_file} with default content")
        
    # Possible unused flags:
    #  -fast
    #  -sync video

    input_flags = [
        "-fflags", "nobuffer",
        "-flags", "low_delay", 
        "-framedrop",
        "-f", "h264",
        "-framerate", "30",
        "-an", # Disable the audio (streamed separately)
        "-noborder",
        "-alwaysontop",
        "-left", f"{1440 - 675}",
        "-top", "0",
        "-window_title", "FRONT CAMERA FEED",
        "-i", "udp://0.0.0.0:8001"
    ]

    # Normal = /Users/fra/Library/Fonts/Mx437_IBM_DOS_ISO8.ttf
    # Bold = /Users/fra/Library/Fonts/Mx437_IBM_VGA_8x16.ttf

    video_filters = [
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
    
    cmd = (
        ["ffplay"] + 
        input_flags + 
        ["-vf"] +
        [",".join(video_filters)]
    )
    
    print("Launching FFplay with the following command:")
    print(" ".join(cmd))
    print("\nPress Ctrl+C to stop the stream")
    
    try:
        # Redirect the output of ffplay to /dev/null
        subprocess.run(cmd, check=True)#, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
    except subprocess.CalledProcessError as e:
        print(f"FFplay exited with error code: {e.returncode}")
        return 1
            
    return 0

if __name__ == "__main__":
    sys.exit(start_ffplay())
    