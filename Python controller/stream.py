
import subprocess
import sys
from pathlib import Path

def main():
    # Ensure /tmp/bw.txt exists (create empty if not)
    bw_file = Path("/tmp/bw.txt")
    if not bw_file.exists():
        bw_file.write_text("468 Kbps")
        print(f"Created {bw_file} with default content")
    
    base_cmd = ["ffplay"]
    
    input_flags = [
        "-fflags", "nobuffer",
        "-flags", "low_delay", 
        "-framedrop",
        "-f", "h264",
        "-framerate", "30",
        #"-fast",
        "-an",              # Disable audio (streamed separately)
        #"-sync", "video",           # Sync to video stream (avoid frame flooding) FIXME:
        "-left", "0",
        "-top", "0",
        "-window_title", "FRONT CAMERA FEED",
        "-i", "udp://0.0.0.0:8001"
    ]

    # Normal = /Users/fra/Library/Fonts/Mx437_IBM_DOS_ISO8.ttf
    # Bold = /Users/fra/Library/Fonts/Mx437_IBM_VGA_8x16.ttf

    video_filters = [
        "scale=640:480",    # No matter what the stream resolution is, always display at 640x480
        "transpose=1",      # 90° rotation clockwise
        #"fps=fps=30",       # Force 30 fps by either dropping or duplicating frames

        # Top center: Static "FRONT CAMERA" text
        "drawtext=fontfile=/Users/fra/Library/Fonts/Mx437_IBM_VGA_8x16.ttf:"
        "text=FRONT CAMERA:"
        "fontsize=h/25:"
        "fontcolor=white:"
        "bordercolor=black:"
        "borderw=1:"
        "x=(w-text_w)/2:"
        "y=20",

        # %Y-%m-%d %H\:%M\:%S
        # %a %b %d %Y

        # Bottom right: Timestamp
        "drawtext='fontfile=/Users/fra/Library/Fonts/Mx437_IBM_DOS_ISO8.ttf:"
        r"text=%{localtime\:%-d %b %Y %X}':"
        "fontsize=h/30:"
        "fontcolor=white:"
        "x=w-text_w-10:"
        "y=h-text_h-10",
        
        # Bottom left: Bandwidth from file (updated every 15 frames)
        "drawtext=fontfile=/Users/fra/Library/Fonts/Mx437_IBM_DOS_ISO8.ttf:"
        "textfile=/tmp/bw.txt:"
        "fontsize=h/30:"
        "fontcolor=white:"
        "x=10:"
        "y=h-text_h-10:"
        "reload=1:"  # Enable file reloading
        "r=2"        # Reload every 2 fps (30fps/15frames = 2fps)
    ]
    
    # Combine all components
    cmd = (
        base_cmd + 
        input_flags + 
        ["-vf"] +
        [",".join(video_filters)]
    )
    
    print("Launching FFplay with the following command:")
    print(" ".join(cmd))
    print("\nPress Ctrl+C to stop the stream")
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
# ...existing code...
        
    except subprocess.CalledProcessError as e:
        print(f"FFplay exited with error code: {e.returncode}")
        return 1
        
    except KeyboardInterrupt:
        print("\nStream stopped by user")
        return 0
            
    return 0

if __name__ == "__main__":
    sys.exit(main())