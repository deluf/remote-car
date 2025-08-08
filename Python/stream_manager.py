
import multiprocessing
import av
import cv2
from datetime import datetime
from enum import Enum
from printer import perror

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

SCALED_WIDTH = int(SCREEN_HEIGHT / ORIGINAL_STREAM_WIDTH * ORIGINAL_STREAM_HEIGHT)

class LENS_FACING(Enum):
    FRONT = 0
    BACK = 1

class FONT_SIZE(Enum):
    SMALL = 0.7
    NORMAL = 1.2
    BIG = 1.7

class Stream_Manager:

    def __init__(self, metrics_queue):
        self.lens_facing = LENS_FACING.FRONT
        self.metrics_queue = metrics_queue
        self.process = None        
        self.font = cv2.FONT_HERSHEY_SIMPLEX

    def _get_text_size(self, text, scale=FONT_SIZE.NORMAL, thickness=5):
        return cv2.getTextSize(text, self.font, scale.value, thickness)[0][0]

    def _draw_text(self, frame, text, position, size=FONT_SIZE.NORMAL, thickness=3):
        
        text_color=(255, 255, 255)
        border_color=(0, 0, 0)
        border_thickness=thickness*2

        # Draw border (black)
        cv2.putText(frame, text, position, self.font, size.value, 
                    border_color, thickness + border_thickness)
        
        # Draw text (white)
        cv2.putText(frame, text, position, self.font, size.value, text_color, thickness)

    def _rotate(self, img):
        """Rotate image based on lens facing"""
        if self.lens_facing == LENS_FACING.FRONT:
            return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        else:
            return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

    def _loop(self):
        try:
            for frame in self.container.decode(video=0):
                frame = frame.to_ndarray(format="bgr24")
                frame = self._rotate(frame)
                frame = cv2.resize(frame, (SCALED_WIDTH*2, SCREEN_HEIGHT*2))
                h, w = frame.shape[:2]

                # Camera source
                text = "FRONT CAMERA" if self.lens_facing == LENS_FACING.FRONT else "BACK CAMERA"
                text_size = self._get_text_size(text, FONT_SIZE.BIG)
                text_x = (w - text_size) // 2
                text_y = h - 20
                self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.BIG)
                
                # Timestamp
                text = datetime.now().strftime("%X")
                text_size = self._get_text_size(text, FONT_SIZE.NORMAL)
                text_x = w - text_size - 20
                text_y = h - 30
                self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.NORMAL)
            
                # Date
                text = datetime.now().strftime("%-d %b %Y")
                text_size = self._get_text_size(text, FONT_SIZE.NORMAL)
                text_x = 20
                text_y = h - 30
                self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.NORMAL)

                cv2.imshow(self.window_name, frame)
                if cv2.waitKey(1) == 27:  # ESC to quit
                    break
                    
        except Exception as e:
            perror(f"Error during playback: {e}")
        finally:
            self.container.close()
            cv2.destroyAllWindows()
            print(f"OK REMOVE THIS")

    def _start(self):
        self.window_name = "VIDEO STREAM"
        cv2.namedWindow(self.window_name, cv2.WINDOW_OPENGL)
        cv2.resizeWindow(self.window_name, SCALED_WIDTH, SCREEN_HEIGHT)
        
        # Position window
        left = (SCREEN_WIDTH - SCALED_WIDTH) // 2
        cv2.moveWindow(self.window_name, left, 0)
        cv2.setWindowProperty(self.window_name, cv2.WND_PROP_TOPMOST, 1)
        
        input_url = f"udp://0.0.0.0:{UDP_PORT}"
        options = {
            "fflags": "nobuffer",
            "flags": "low_delay",
            "framedrop": "1"
        }
        self.container = av.open(input_url, format="h264", mode="r", options=options)

        self._loop()

    def play(self):
        self.process = multiprocessing.Process(target=self._start)
        self.process.start()
        print(f"Stream starting...")

    def switch(self):
        self.lens_facing = LENS_FACING.FRONT if self.lens_facing == LENS_FACING.BACK else LENS_FACING.BACK

    def close(self):
        if self.process:
            self.process.terminate()
        print(f"Stream terminated")
