import multiprocessing
import queue
import shutil
import sys
import threading
import time
from datetime import datetime
from enum import Enum
import av
import cv2
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
from printer import perror
from server import METRIC, STREAM_METRICS

if shutil.which("ffmpeg") is None:
    perror("ffmpeg is not installed or not found in PATH")

# Stream parameters
ORIGINAL_STREAM_WIDTH = 320
ORIGINAL_STREAM_HEIGHT = 240
FRAMERATE = 30
UDP_PORT = 8001
FRAMETIME_MS = int(1 / FRAMERATE * 1000)

# Device parameters
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900
SCALED_WIDTH = int(SCREEN_HEIGHT / ORIGINAL_STREAM_WIDTH * ORIGINAL_STREAM_HEIGHT)

class LensFacing(Enum):
    FRONT = 0
    BACK = 1

class FontSize(Enum):
    SMALL = 0.7
    NORMAL = 1.2
    BIG = 1.7
    HUGE = 2.2

class Icon(Enum):
    GAS = 0
    BATTERY_EMPTY = 1
    BATTERY_LOW = 2
    BATTERY_HIGH = 3
    BATTERY_FULL = 4
    SIGNAL_EMPTY = 5
    SIGNAL_LOW = 6
    SIGNAL_HIGH = 7
    SIGNAL_FULL = 8
    LIGHTNING = 9

class StreamManager:
    def __init__(self, metrics_queue):
        self.metrics_queue = metrics_queue
        self.metrics = {metric: 0 for metric in STREAM_METRICS}
        self.no_signal_threshold_s = 1
        self.last_frame_time = 0
        self.process = None
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.text_thickness = 2
        self.border_thickness = 7
        self.num_cells_in_series = 2

        # Load icons ensuring alpha channel is loaded properly
        self.icons = {icon: cv2.imread(f"icons/{icon.name.lower()}.png", cv2.IMREAD_UNCHANGED) for icon in Icon}

        # Shared state between processes
        self.lens_facing_shared = multiprocessing.Value('i', LensFacing.FRONT.value)

        # GUI placeholders
        self.app = None
        self.window = None
        self.label = None
        self.frame_queue = None

    def _get_text_size(self, text, scale=FontSize.NORMAL):
        return cv2.getTextSize(text, self.font, scale.value, self.text_thickness)[0]

    def _draw_text(self, frame, text, position, size=FontSize.NORMAL, color=(255, 255, 255)):
        # Draw black border
        cv2.putText(frame, text, position, self.font, size.value, 
                    (0, 0, 0), self.text_thickness + self.border_thickness, cv2.LINE_AA)
        # Draw white text
        cv2.putText(frame, text, position, self.font, size.value, 
                    color, self.text_thickness, cv2.LINE_AA)

    def _draw_icon(self, frame, icon, position):
        icon_img = self.icons[icon]
        h, w = icon_img.shape[:2]
        x, y = position
        
        # Center the icon in the y position
        y -= h // 2
        
        # Blend the icon using alpha channel
        alpha = icon_img[:, :, 3] / 255.0
        for c in range(3):
            frame[y:y+h, x:x+w, c] = alpha * icon_img[:, :, c] + (1 - alpha) * frame[y:y+h, x:x+w, c]

    def _get_lens_facing(self):
        return LensFacing(self.lens_facing_shared.value)

    def _rotate(self, img):
        if self._get_lens_facing() == LensFacing.FRONT:
            return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        else:
            return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

    def _create_no_signal_frame(self):
        frame = np.zeros((SCREEN_HEIGHT * 2, SCALED_WIDTH * 2, 3), dtype=np.uint8)
        h, w = frame.shape[:2]
        
        text = "- NO SIGNAL -"
        (text_w, text_h) = self._get_text_size(text, FontSize.HUGE)
        text_x = (w - text_w) // 2
        text_y = (h + text_h) // 2
        self._draw_text(frame, text, (text_x, text_y), FontSize.HUGE)
        
        return frame

    def _voltage_to_percentage(self, voltage):
        single_cell_voltage = voltage / self.num_cells_in_series
        pct = (single_cell_voltage - 3.2) * 100
        return max(0, min(100, round(pct)))

    def _draw_voltage_metric(self, frame, metric, icon, low_text, y_pos, warning_y_under_center, w, h, padding, icon_size, space):
        voltage = self.metrics[metric] / 10.0
        percentage = self._voltage_to_percentage(voltage)

        if percentage >= 50:
            color = (255, 255, 255)
        elif percentage >= 25:
            color = (0, 140, 255)
        else:
            color = (0, 0, 180)
            # Blinking warning text
            if int(time.time()) % 2 == 0:
                (text_w, text_h) = self._get_text_size(low_text, FontSize.HUGE)
                text_x = (w - text_w) // 2
                text_y = h // 2 + (text_h + space if warning_y_under_center else -space)
                self._draw_text(frame, low_text, (text_x, text_y), FontSize.HUGE, color)

        text_v = f"{voltage:.1f}V"
        (text_v_w, text_v_h) = self._get_text_size(text_v, FontSize.BIG)
        if y_pos is None:
            y_pos = padding + text_v_h

        self._draw_text(frame, text_v, (padding + icon_size + space, y_pos), FontSize.BIG)
        self._draw_icon(frame, icon, (padding, y_pos - text_v_h // 2))

        text_p = f"~{percentage}%"
        self._draw_text(frame, text_p, (padding + icon_size + space + text_v_w + space, y_pos), FontSize.BIG, color)

    def _add_overlays(self, frame):
        h, w = frame.shape[:2]
        padding = 30
        space = 10
        icon_size = 64

        # Camera source overlay
        lens_facing = self._get_lens_facing()
        text = "FRONT CAMERA" if lens_facing == LensFacing.FRONT else "BACK CAMERA"
        (text_w, text_h) = self._get_text_size(text, FontSize.BIG)
        self._draw_text(frame, text, ((w - text_w) // 2, padding + text_h), FontSize.BIG)
        
        # Timestamp overlay
        text = datetime.now().strftime("%X")
        (text_w, text_h) = self._get_text_size(text, FontSize.NORMAL)
        self._draw_text(frame, text, (w - text_w - padding, h - padding), FontSize.NORMAL)
    
        # Date overlay
        text = datetime.now().strftime("%-d %b %Y")
        (text_w, text_h) = self._get_text_size(text, FontSize.NORMAL)
        self._draw_text(frame, text, (padding, h - padding), FontSize.NORMAL)

        # Phone battery overlay
        phone_pct = self.metrics[METRIC.PHONE_BATTERY_PERCENT]
        if phone_pct >= 80:
            icon = Icon.BATTERY_FULL
            color = (255, 255, 255)
        elif phone_pct >= 50:
            icon = Icon.BATTERY_HIGH
            color = (255, 255, 255)
        elif phone_pct >= 25:
            icon = Icon.BATTERY_LOW
            color = (0, 140, 255)
        else:
            icon = Icon.BATTERY_EMPTY
            color = (0, 0, 180)
        
        text = f"{phone_pct}%"
        (text_w, text_h) = self._get_text_size(text, FontSize.BIG)
        text_x = w - text_w - padding
        text_y = padding + text_h
        self._draw_text(frame, text, (text_x, text_y), FontSize.BIG, color)
        self._draw_icon(frame, icon, (text_x - icon_size, text_y - text_h // 2))

        # LTE Signal overlay
        signal_level = self.metrics[METRIC.SIGNAL_LEVEL]
        if signal_level >= 4:
            icon = Icon.SIGNAL_FULL
        elif signal_level == 3:
            icon = Icon.SIGNAL_HIGH
        elif signal_level == 2:
            icon = Icon.SIGNAL_LOW
        else:
            icon = Icon.SIGNAL_EMPTY
        
        text = "LTE"
        (text_w, text_h) = self._get_text_size(text, FontSize.BIG)
        text_x = w - text_w - padding
        text_y = padding + text_h + 70
        self._draw_text(frame, text, (text_x, text_y), FontSize.BIG)
        self._draw_icon(frame, icon, (text_x - icon_size - space, text_y - text_h // 2))

        # Car battery voltage overlay
        self._draw_voltage_metric(
            frame, METRIC.CAR_BATTERY_VOLTAGE, Icon.GAS, "- CAR BATTERY LOW -",
            None, False, w, h, padding, icon_size, space
        )

        # Electronics battery voltage overlay
        self._draw_voltage_metric(
            frame, METRIC.ELECTRONICS_BATTERY_VOLTAGE, Icon.LIGHTNING, "- ELECTRONICS BATTERY LOW -",
            padding + icon_size * 2 - space * 2, True, w, h, padding, icon_size, space
        )

        # Heading overlay
        heading = self.metrics[METRIC.HEADING]
        text = f"- {heading}' -"
        (text_w, text_h) = self._get_text_size(text, FontSize.NORMAL)
        self._draw_text(frame, text, ((w - text_w) // 2, h - padding - 55), FontSize.NORMAL)

        cardinal = self._heading_to_cardinal(heading)
        (text_w, text_h) = self._get_text_size(cardinal, FontSize.BIG)
        self._draw_text(frame, cardinal, ((w - text_w) // 2, h - padding), FontSize.BIG)

    def _heading_to_cardinal(self, degrees):
        directions = ["NORTH", "NORTH EAST", "EAST", "SOUTH EAST", "SOUTH", "SOUTH WEST", "WEST", "NORTH WEST"]
        index = int((degrees + 22.5) // 45) % 8
        return directions[index]

    def _telemetry_updater_thread(self):
        while True:
            metric, value = self.metrics_queue.get()
            self.metrics[metric] = value

    def _stream_reader_thread(self):
        stream = None
        try:
            options = {"fflags": "nobuffer", "flags": "low_delay", "framedrop": "1"}
            stream = av.open(f"udp://0.0.0.0:{UDP_PORT}", format="h264", mode="r", options=options)
            for frame in stream.decode(video=0):
                img = frame.to_ndarray(format="bgr24")
                img = self._rotate(img)
                img = cv2.resize(img, (SCALED_WIDTH * 2, SCREEN_HEIGHT * 2))
                try:
                    self.frame_queue.put_nowait(img)
                    self.last_frame_time = time.time()
                except queue.Full:
                    pass
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
            # Convert BGR -> RGB for Qt
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
            pix = QtGui.QPixmap.fromImage(qimg)

            # Scale to label preserving aspect ratio
            pix = pix.scaled(self.label.width(), self.label.height(), QtCore.Qt.KeepAspectRatio)
            self.label.setPixmap(pix)

    def _start(self):
        self.app = QtWidgets.QApplication(sys.argv)

        self.window = QtWidgets.QWidget()
        self.window.setWindowTitle("VIDEO STREAM")
        self.window.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)

        self.label = QtWidgets.QLabel()
        self.label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.label.setAlignment(QtCore.Qt.AlignCenter)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self.window.setLayout(layout)

        # Size and center geometry
        left = (SCREEN_WIDTH - SCALED_WIDTH) // 2
        self.window.setGeometry(left, 0, SCALED_WIDTH, SCREEN_HEIGHT)

        no_signal = self._create_no_signal_frame()
        rgb = cv2.cvtColor(no_signal, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
        pix = QtGui.QPixmap.fromImage(qimg)
        pix = pix.scaled(SCALED_WIDTH, SCREEN_HEIGHT, QtCore.Qt.KeepAspectRatio)
        self.label.setPixmap(pix)

        self.window.show()
        self.frame_queue = queue.Queue(maxsize=1)

        threading.Thread(target=self._stream_reader_thread, daemon=True).start()
        threading.Thread(target=self._telemetry_updater_thread, daemon=True).start()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._update_display)
        self.timer.start(FRAMETIME_MS)

        try:
            self.app.exec_()
        except Exception as e:
            perror(f"Qt exec error: {e}")
        finally:
            try:
                self.app.quit()
            except Exception:
                pass

    def switch(self):
        curr = self.lens_facing_shared.value
        new_val = LensFacing.BACK.value if curr == LensFacing.FRONT.value else LensFacing.FRONT.value
        self.lens_facing_shared.value = new_val
        print(f"Switched to {'FRONT' if new_val == LensFacing.FRONT.value else 'BACK'} camera")

    def play(self):
        if self.process and self.process.is_alive():
            print("STREAM MANAGER process already launched")
            return
        self.process = multiprocessing.Process(target=self._start)
        self.process.start()
        print("STREAM MANAGER process launched")

    def close(self):
        if self.process:
            self.process.terminate()
            self.process = None
        print("STREAM MANAGER process terminated")
