
import shutil
from printer import perror
if shutil.which("ffmpeg") is None:
    perror("ffmpeg is not installed or not found in PATH")

import multiprocessing
import queue
import av
import cv2
import numpy as np
import time
import threading
from datetime import datetime
from enum import Enum
from PyQt5 import QtWidgets, QtGui, QtCore
import sys

from server import METRIC, STREAM_METRICS
from printer import perror

# Stream parameters
ORIGINAL_STREAM_WIDTH = 320
ORIGINAL_STREAM_HEIGHT = 240
FRAMERATE = 30
UDP_PORT = 8001
FRAMETIME_MS = int(1/FRAMERATE * 1000)

# Device parameters
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900
SCALED_WIDTH = int(SCREEN_HEIGHT / ORIGINAL_STREAM_WIDTH * ORIGINAL_STREAM_HEIGHT)

class LENS_FACING(Enum):
    FRONT = 0
    BACK = 1

class FONT_SIZE(Enum):
    SMALL = 0.7
    NORMAL = 1.2
    BIG = 1.7
    HUGE = 2.2

class ICON(Enum):
    GAS = 0
    BATTERY_EMPTY = 1
    BATTERY_LOW = 2
    BATTERY_HIGH = 3
    BATTERY_FULL = 4
    SIGNAL_EMPTY = 5
    SIGNAL_LOW = 6
    SIGNAL_HIGH = 7
    SIGNAL_FULL = 8

class Stream_Manager:

    def __init__(self, metrics_queue):
        self.metrics_queue = metrics_queue
        self.metrics = { metric: 0 for metric in STREAM_METRICS }
        self.no_signal_threshold_s = 1
        self.last_frame_time = 0
        self.process = None
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.text_thickness = 2
        self.border_thickness = 7
        self.num_cells_in_series = 2

        # cv2.IMREAD_UNCHANGED ensures alpha channel is loaded properly
        self.icons = { icon: cv2.imread(f"icons/{icon.name.lower()}.png", cv2.IMREAD_UNCHANGED) for icon in ICON}

        # Shared state between processes FIXME:
        self.lens_facing_shared = multiprocessing.Value('i', LENS_FACING.FRONT.value)

        # GUI placeholders (set in _start)
        self.app = None
        self.window = None
        self.label = None
        self.frame_queue = None

    def _get_text_size(self, text, scale=FONT_SIZE.NORMAL):
        return cv2.getTextSize(text, self.font, scale.value, self.text_thickness)[0]

    def _draw_text(self, frame, text, position, size=FONT_SIZE.NORMAL, color=(255,255,255)):
        # Draw border (black)
        border_color = (0, 0, 0)
        cv2.putText(frame, text, position, self.font, size.value, 
            border_color, self.text_thickness + self.border_thickness, cv2.LINE_AA)
        
        # Draw text (white)
        cv2.putText(frame, text, position, self.font, size.value, 
            color, self.text_thickness, cv2.LINE_AA)
        
        
    def _draw_icon(self, frame, icon, position):
        icon_img = self.icons[icon]
        h, w = icon_img.shape[:2]
        x, y = position
        
        # Center the incon in the y position
        y -= h//2
        
        # Blend the icon with the frame using alpha channel (png's transparency is preserved)
        alpha = icon_img[:, :, 3] / 255.0
        for c in range(3):
            frame[y:y+h, x:x+w, c] = alpha * icon_img[:, :, c] + (1 - alpha) * frame[y:y+h, x:x+w, c]

    def _get_lens_facing(self):
        return LENS_FACING(self.lens_facing_shared.value)

    def _rotate(self, img):
        if self._get_lens_facing() == LENS_FACING.FRONT:
            return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        else:
            return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

    def _create_no_signal_frame(self):
        frame = np.zeros((SCREEN_HEIGHT*2, SCALED_WIDTH*2, 3), dtype=np.uint8)
        h, w = frame.shape[:2]
        
        text = "- NO SIGNAL -"
        (text_w, text_h)= self._get_text_size(text, FONT_SIZE.HUGE)
        text_x = (w - text_w) // 2
        text_y = (h + text_h) // 2
        self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.HUGE)
        
        self._add_overlays(frame) # FIXME:
        return frame

    def _rc_voltage_to_percentage(self, voltage):
        single_cell_voltage = voltage / self.num_cells_in_series
        single_cell_full = 4.2
        single_cell_empty = 3.2
        if single_cell_voltage >= single_cell_full:
            return 100
        if single_cell_voltage <= single_cell_empty:
            return 0
        return round((single_cell_voltage - single_cell_empty) * 100)

    def _add_overlays(self, frame):
        h, w = frame.shape[:2]
        padding = 30
        space = 10
        icon_size = 64

        # Camera source
        lens_facing = self._get_lens_facing()
        text = "FRONT CAMERA" if lens_facing == LENS_FACING.FRONT else "BACK CAMERA"
        (text_w, text_h)= self._get_text_size(text, FONT_SIZE.BIG)
        text_x = (w - text_w) // 2
        text_y = padding + text_h
        self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.BIG)
        
        # Timestamp
        text = datetime.now().strftime("%X")
        (text_w, text_h)= self._get_text_size(text, FONT_SIZE.NORMAL)
        text_x = w - text_w - padding
        text_y = h - padding
        self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.NORMAL)
    
        # Date
        text = datetime.now().strftime("%-d %b %Y")
        (text_w, text_h)= self._get_text_size(text, FONT_SIZE.NORMAL)
        text_x = padding
        text_y = h - padding
        self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.NORMAL)

        # Battery
        battey_percent = self.metrics[METRIC.PHONE_BATTERY_PERCENT]
        if battey_percent >= 80:
            icon = ICON.BATTERY_FULL
            color = (255, 255, 255)
        elif battey_percent >= 50:
            icon = ICON.BATTERY_HIGH
            color = (255, 255, 255)
        elif battey_percent >= 25:
            icon = ICON.BATTERY_LOW
            color = (0, 140, 255)
        else:
            icon = ICON.BATTERY_EMPTY
            color = (0, 0, 180)
        
        text = f"{battey_percent}%"
        (text_w, text_h)= self._get_text_size(text, FONT_SIZE.BIG)
        text_x = w - text_w - padding
        text_y = padding + text_h
        self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.BIG, color)
        self._draw_icon(frame, icon, (text_x - icon_size, text_y - text_h//2))

        # Signal
        signal_level = self.metrics[METRIC.SIGNAL_LEVEL]

        if signal_level >= 4:
            icon = ICON.SIGNAL_FULL
        elif signal_level == 3:
            icon = ICON.SIGNAL_HIGH
        elif signal_level == 2:
            icon = ICON.SIGNAL_LOW
        else:
            icon = ICON.SIGNAL_EMPTY
        
        text = "LTE"
        (text_w, text_h)= self._get_text_size(text, FONT_SIZE.BIG)
        text_x = w - text_w - padding
        text_y = padding + text_h + 70
        self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.BIG)
        self._draw_icon(frame, icon, (text_x - icon_size - space, text_y - text_h//2))

        # Voltage
        voltage = self.metrics[METRIC.CAR_BATTERY_VOLTAGE]/10.0    
        percentage = self._rc_voltage_to_percentage(voltage)

        if percentage >= 50:
            color = (255, 255, 255)
        elif percentage >= 25:
            color = (0, 140, 255)
        else:
            color = (0, 0, 180)
            # Blinking battery low text
            if (int(time.time()) % 2 == 0):
                text = "- CAR BATTERY LOW -"
                (text_w, text_h)= self._get_text_size(text, FONT_SIZE.HUGE)
                text_x = (w - text_w) // 2
                text_y = (h + text_h) // 2
                self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.HUGE, color)

        text = f"{voltage:.1f}V"
        (text_w, text_h)= self._get_text_size(text, FONT_SIZE.BIG)
        text_x = padding + icon_size + space
        text_y = padding + text_h
        self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.BIG)
        self._draw_icon(frame, ICON.GAS, (padding, text_y - text_h//2))
    
        text = f"~{percentage}%"
        (text_w, text_h)= self._get_text_size(text, FONT_SIZE.BIG)
        text_x = padding + space
        text_y = padding + text_h + 70
        self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.BIG, color)

        # Heading
        text = f"- {self.metrics[METRIC.HEADING]}' -"
        (text_w, text_h)= self._get_text_size(text, FONT_SIZE.NORMAL)
        text_x = (w - text_w) // 2
        text_y = h - padding - 55
        self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.NORMAL)

        text = self._heading_to_cardinal(self.metrics[METRIC.HEADING])
        (text_w, text_h)= self._get_text_size(text, FONT_SIZE.BIG)
        text_x = (w - text_w) // 2
        text_y = h - padding
        self._draw_text(frame, text, (text_x, text_y), FONT_SIZE.BIG)

    def _heading_to_cardinal(self, degrees):
        directions = [
            "NORTH", 
            "NORTH EAST", 
            "EAST", 
            "SOUTH EAST", 
            "SOUTH", 
            "SOUTH WEST", 
            "WEST", 
            "NORTH WEST"
        ]        
        # Each sector is 45°, offset by 22.5° for correct rounding
        index = int((degrees + 22.5) // 45) % 8
        return directions[index]

    def _telemetry_updater_thread(self):
        while True:
            (metric, value) = self.metrics_queue.get()
            self.metrics[metric] = value

    def _stream_reader_thread(self):
        try:
            input_url = f"udp://0.0.0.0:{UDP_PORT}"
            options = {
                "fflags": "nobuffer",
                "flags": "low_delay",
                "framedrop": "1"
            }
            stream = av.open(input_url, format="h264", mode="r", options=options)
            
            for frame in stream.decode(video=0):
                frame = frame.to_ndarray(format="bgr24")
                frame = self._rotate(frame)
                frame = cv2.resize(frame, (SCALED_WIDTH*2, SCREEN_HEIGHT*2))
                
                try:
                    self.frame_queue.put_nowait(frame)
                    self.last_frame_time = time.time()
                except queue.Full:
                    pass  # Queue full, skip frame
                    
        except Exception as e:
            perror(f"Stream reader error: {e}")
        finally:
            if stream:
                stream.close()

    def _update_display(self):
        frame = None
        try:
            frame = self.frame_queue.get_nowait()
        except queue.Empty:
            pass
        else:
            self._add_overlays(frame)

        timed_out = time.time() - self.last_frame_time > self.no_signal_threshold_s
        if frame is None and timed_out:
            frame = self._create_no_signal_frame()

        if frame is not None:
            # convert BGR -> RGB for Qt
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qimg = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
            pix = QtGui.QPixmap.fromImage(qimg)

            # scale to label/window if needed preserving aspect
            pix = pix.scaled(self.label.width(), self.label.height(), QtCore.Qt.KeepAspectRatio)
            self.label.setPixmap(pix)

    def _start(self):
        self.app = QtWidgets.QApplication(sys.argv)

        self.window = QtWidgets.QWidget()
        self.window.setWindowTitle("VIDEO STREAM")
        self.window.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)

        # Create QLabel to hold frames
        self.label = QtWidgets.QLabel()
        # make sure label expands to full window
        self.label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.label.setAlignment(QtCore.Qt.AlignCenter)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self.window.setLayout(layout)

        # Position and size the window (match behavior of your cv2 move/resize)
        window_w = SCALED_WIDTH
        window_h = SCREEN_HEIGHT
        left = (SCREEN_WIDTH - SCALED_WIDTH) // 2
        top = 0
        # set geometry (x, y, width, height)
        self.window.setGeometry(left, top, window_w, window_h)

        # Initially show NO SIGNAL
        no_signal_frame = self._create_no_signal_frame()
        rgb = cv2.cvtColor(no_signal_frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(qimg)
        pix = pix.scaled(window_w, window_h, QtCore.Qt.KeepAspectRatio)
        self.label.setPixmap(pix)

        self.window.show()

        self.frame_queue = queue.Queue(maxsize=1)

        threading.Thread(target=self._stream_reader_thread, daemon=True).start()
        threading.Thread(target=self._telemetry_updater_thread, daemon=True).start()

        timer = QtCore.QTimer()
        timer.timeout.connect(self._update_display)
        timer.start(FRAMETIME_MS)

        # Run the Qt event loop (blocks until window closed)
        try:
            self.app.exec_()
        except Exception as e:
            perror(f"Qt exec error: {e}")
        finally:
            # cleanup
            try:
                self.app.quit()
            except Exception:
                pass

    def switch(self):
        # FIXME: thrash
        current_value = self.lens_facing_shared.value
        new_value = LENS_FACING.BACK.value if current_value == LENS_FACING.FRONT.value else LENS_FACING.FRONT.value
        self.lens_facing_shared.value = new_value
        print(f"Switched to {'FRONT' if new_value == LENS_FACING.FRONT.value else 'BACK'} camera")

    def play(self):
        if self.process and self.process.is_alive():
            print("Stream already started")
            return

        self.process = multiprocessing.Process(target=self._start)
        self.process.start()
        print("Stream started")

    def close(self):
        if self.process:
            self.process.terminate()
            self.process = None
        print("Stream terminated (PyQt)")
