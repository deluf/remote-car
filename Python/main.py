import os
import multiprocessing
import time
from enum import Enum, IntEnum
import pygame

# Set environment variables for SDL
os.environ['SDL_VIDEO_WINDOW_POS'] = "0,0"
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

from server import METRIC, STREAM_METRICS, TEMP_METRICS, Server
from gps_tracker import GPSTracker
from stream_manager import StreamManager
from printer import perror
from gamepad_viewer import GamepadViewer
from network_manager import NetworkManager

class DS4Digital(Enum):
    X = 0
    CIRCLE = 1
    SQUARE = 2
    TRIANGLE = 3
    SHARE = 4
    PS = 5
    OPTIONS = 6
    L3 = 7
    R3 = 8
    L1 = 9
    R1 = 10
    UP = 11
    DOWN = 12
    LEFT = 13
    RIGHT = 14
    TOUCHPAD = 15

class DS4Analog(Enum):
    L_X = 0     # -1 Left -> Right 1
    L_Y = 1     # -1 Up -> Down 1
    R_X = 2     # -1 Left -> Right 1
    R_Y = 3     # -1 Up -> Down 1
    L2 = 4      # -1 Out -> In 1
    R2 = 5      # -1 Out -> In 1

class Command(IntEnum):
    FORWARD = 0
    BACKWARD = 50
    RIGHT = 100
    LEFT = 150
    SWITCH_CAMERA = 200
    TOGGLE_CLACSON = 201
    TOGGLE_NEON = 202

COMMAND_INTENSITY_MAX = 50
FPS = 30
STICK_DEADZONE = 0.75
TRIGGER_DEADZONE = 0.01

RED_LIMITS = {
    METRIC.MODEM_TEMP: 60,
    METRIC.CAMERA_TEMP: 60,
    METRIC.CPU_TEMP: 70,
    METRIC.GPU_TEMP: 70,
    METRIC.BATTERY_TEMP: 45,
}

ORANGE_LIMITS = {
    METRIC.MODEM_TEMP: 45,
    METRIC.CAMERA_TEMP: 45,
    METRIC.CPU_TEMP: 55,
    METRIC.GPU_TEMP: 55,
    METRIC.BATTERY_TEMP: 37.5,
}

def calculate_march_intensity(level):
    if level < -1 + TRIGGER_DEADZONE:
        return 0
    if level > 1 - TRIGGER_DEADZONE:
        return COMMAND_INTENSITY_MAX - 1
    
    # -1 <-> 1 remapped to 0 <-> 49
    pct = (level + 1) / 2
    return round(pct * (COMMAND_INTENSITY_MAX - 1))

def calculate_steer_intensity(level):
    if abs(level) < STICK_DEADZONE:
        return 0
    return COMMAND_INTENSITY_MAX - 1

class RCApp:
    def __init__(self):
        self.gamepad_viewer = GamepadViewer()
        self.gps_tracker = GPSTracker()
        self.network_manager = NetworkManager()
        self.server = Server(self.telemetry_callback)
        self.metrics_queue = multiprocessing.Queue()
        self.video_stream = StreamManager(self.metrics_queue)

        self.last_temps = {metric: 0.0 for metric in TEMP_METRICS}
        self.max_temps = {metric: 0.0 for metric in TEMP_METRICS}
        self.last_sent_states = {direction: 0 for direction in Command}

        self.has_focus = False
        self.joystick = None
        self.screen = None
        self.clock = None
        self.font = None
        self.max_len = max(len(m.name.removesuffix("_TEMP")) for m in TEMP_METRICS)

    def draw_temp(self, surface, metric, position):
        name = metric.name.removesuffix("_TEMP")
        text = f"{name:<{self.max_len}}      {self.max_temps[metric]:>3} °C"
        text_surface = self.font.render(text, True, (0, 0, 0))
        surface.blit(text_surface, position)

        text_val = f"{' ' * self.max_len} {self.last_temps[metric]:>3}"
        val = self.last_temps[metric]
        if val >= RED_LIMITS[metric]:
            color = (180, 0, 0)
        elif val >= ORANGE_LIMITS[metric]:
            color = (255, 140, 0)
        else:
            color = (0, 0, 0)
        text_surface = self.font.render(text_val, True, color)
        surface.blit(text_surface, position)

    def telemetry_callback(self, metric, value):
        if metric == METRIC.POSITION:
            self.gps_tracker.add_waypoint(value[0], value[1], value[2])
        elif metric in STREAM_METRICS:
            self.metrics_queue.put_nowait((metric, value))
        elif metric in TEMP_METRICS:
            self.last_temps[metric] = value
            if self.max_temps[metric] < value:
                self.max_temps[metric] = value
        else:
            perror(f"Unhandled metric {metric.name}: {value}")

    def should_send(self, direction, intensity):
        if self.last_sent_states[direction] == intensity:
            return False
        self.last_sent_states[direction] = intensity
        return True

    def ui_loop(self):
        self.screen = pygame.display.set_mode((382, 320), pygame.NOFRAME)
        pygame.display.set_caption("RC++")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("mx437ibmvga8x16", 28)

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                elif event.type == pygame.WINDOWFOCUSGAINED:
                    self.has_focus = True
                elif event.type == pygame.WINDOWFOCUSLOST:
                    self.has_focus = False
                elif event.type == pygame.JOYBUTTONDOWN:
                    try:
                        button = DS4Digital(event.button)
                    except ValueError:
                        continue
                    
                    if button == DS4Digital.TOUCHPAD:
                        return
                    elif button == DS4Digital.TRIANGLE:
                        self.server.send_command(Command.SWITCH_CAMERA.to_bytes(1))
                        self.video_stream.switch()
                    elif button == DS4Digital.SQUARE:
                        self.server.send_command(Command.TOGGLE_NEON.to_bytes(1))
                    elif button == DS4Digital.X:
                        self.server.send_command(Command.TOGGLE_CLACSON.to_bytes(1))
                elif event.type == pygame.JOYBUTTONUP:
                    try:
                        button = DS4Digital(event.button)
                    except ValueError:
                        continue
                    
                    if button == DS4Digital.X:
                        self.server.send_command(Command.TOGGLE_CLACSON.to_bytes(1))
                elif event.type == pygame.JOYAXISMOTION:
                    try:
                        analog = DS4Analog(event.axis)
                    except ValueError:
                        continue
                    
                    val = event.value
                    direction, intensity = None, None

                    if analog == DS4Analog.R2:
                        direction = Command.FORWARD
                        intensity = calculate_march_intensity(val)
                    elif analog == DS4Analog.L2:
                        direction = Command.BACKWARD
                        intensity = calculate_march_intensity(val)
                    elif analog == DS4Analog.L_X:
                        direction = Command.LEFT if val < 0 else Command.RIGHT
                        intensity = calculate_steer_intensity(val)

                    if direction is not None and intensity is not None:
                        if self.should_send(direction, intensity):
                            cmd_val = direction + intensity
                            self.server.send_command(cmd_val.to_bytes(1))
                elif event.type == pygame.JOYDEVICEADDED:
                    self.joystick = pygame.joystick.Joystick(event.device_index)
                    print(f"{self.joystick.get_name()} connected")
                elif event.type == pygame.JOYDEVICEREMOVED:
                    print("Joystick disconnected")
                    self.joystick = None

            if not self.has_focus:
                colors = [(255, 255, 255), (0, 0, 0)]
                self.screen.fill(colors[int(time.time()) % 2])
            else:
                self.screen.fill((255, 255, 255))

            header = f"{' ' * self.max_len} LAST  MAX"
            text_surface = self.font.render(header, True, (0, 0, 0))
            self.screen.blit(text_surface, (50, 30))

            for index, metric in enumerate(TEMP_METRICS):
                self.draw_temp(self.screen, metric, (50, index * 30 + 60))

            pygame.display.flip()
            self.clock.tick(FPS)

    def run(self):
        pygame.init()
        self.gamepad_viewer.start_mirroring()
        self.gps_tracker.open_live_map()
        self.network_manager.start_monitoring()
        self.server.start()
        self.video_stream.play()

        try:
            self.ui_loop()
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()

    def cleanup(self):
        self.gamepad_viewer.stop_mirroring()
        self.gps_tracker.close_live_map()
        self.network_manager.stop_monitoring()
        self.video_stream.close()
        self.server.stop()
        pygame.quit()
        print("Done")

if __name__ == "__main__":
    app = RCApp()
    app.run()
