
import os
os.environ['SDL_VIDEO_WINDOW_POS'] = "0,0"
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import multiprocessing
import pygame
from enum import Enum, IntEnum
import time

from server import METRIC, STREAM_METRICS, TEMP_METRICS, Server
from gps_tracker import GPS_Tracker
from stream_manager import Stream_Manager
from printer import perror
from gamepad_viewer import Gamepad_Viewer
from network_manager import Network_Manager

class DS4_DIGITAL(Enum):
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

class DS4_ANALOG(Enum):
    L_X = 0     # -1 Left -> Right 1
    L_Y = 1     # -1 Up   -> Down 1
    R_X = 2     # -1 Left -> Right 1
    R_Y = 3     # -1 Up   -> Down 1
    L2 = 4      # -1 Out  -> In 1
    R2 = 5      # -1 Out  -> In 1

class COMMAND(IntEnum):
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

#FIXME: color anche le max, magari aggiungi host temp
red_limit = {
    METRIC.MODEM_TEMP: 60,
    METRIC.CAMERA_TEMP: 60,
    METRIC.CPU_TEMP: 70,
    METRIC.GPU_TEMP: 70,
    METRIC.BATTERY_TEMP: 45,
}
orange_limit = {
    METRIC.MODEM_TEMP: 45,
    METRIC.CAMERA_TEMP: 45,
    METRIC.CPU_TEMP: 55,
    METRIC.GPU_TEMP: 55,
    METRIC.BATTERY_TEMP: 37.5,
}
last_temps = {temp_metric: 0 for temp_metric in TEMP_METRICS}
max_temps = {temp_metric: 0 for temp_metric in TEMP_METRICS}
max_len = max(len(m.name.removesuffix("_TEMP")) for m in TEMP_METRICS)
def draw_temp(surface, temp_metric, position):
    text = f"{temp_metric.name.removesuffix("_TEMP"):<{max_len}} {" "*4}  {max_temps[temp_metric]:>3} °C"
    text_surface = PYGAME_FONT.render(text, True, (0,0,0))
    surface.blit(text_surface, position)

    text = f"{" " * max_len} {last_temps[temp_metric]:>3}"
    if last_temps[temp_metric] >= red_limit[temp_metric]:
        color = (180, 0, 0)
    elif last_temps[temp_metric] >= orange_limit[temp_metric]:
        color = (255, 140, 0)
    else:
        color = (0, 0, 0)
    text_surface = PYGAME_FONT.render(text, True, color)
    surface.blit(text_surface, position)

def telemetry_callback(metric, value):
    if metric == METRIC.POSITION:
        gps_tracker.add_waypoint(value[0], value[1], value[2])
    elif metric in STREAM_METRICS:
        metrics_queue.put_nowait((metric, value))
    elif metric in TEMP_METRICS:
        last_temps[metric] = value
        if max_temps[metric] < value:
            max_temps[metric] = value
    else:
        perror(f"Unhandled metric {metric.name}: {value}")

def calculate_march_intensity(level):
    if level < -1 + TRIGGER_DEADZONE:
        return 0
    if level > 1 - TRIGGER_DEADZONE:
        return COMMAND_INTENSITY_MAX - 1
    
    # -1 <-> 1 remapped to 0 <-> 49
    level_percent = (level + 1)/2 
    return round(level_percent * (COMMAND_INTENSITY_MAX - 1))

def calculate_steer_intensity(level):
    if abs(level) < STICK_DEADZONE:
        return 0
    if abs(level) > 1 - STICK_DEADZONE:
        return COMMAND_INTENSITY_MAX - 1
    
    return COMMAND_INTENSITY_MAX - 1

# State tracking for bandwidth optimization
last_sent_states = { direction: 0 for direction in COMMAND }
def should_send(direction, intensity):
    if last_sent_states[direction] == intensity:
        return False
    last_sent_states[direction] = intensity
    return True

def ui_loop():
    screen = pygame.display.set_mode((382, 320), pygame.NOFRAME)
    pygame.display.set_caption("RC++")
    clock = pygame.time.Clock()

    has_focus = False
    joystick = None
    while True:

        for event in pygame.event.get():
            
            if event.type == pygame.WINDOWFOCUSGAINED:
                has_focus = True
            elif event.type == pygame.WINDOWFOCUSLOST:
                has_focus = False

            if event.type == pygame.JOYBUTTONDOWN:
                button = DS4_DIGITAL(event.button)
                if button == DS4_DIGITAL.TOUCHPAD:
                    return
                elif button == DS4_DIGITAL.TRIANGLE:
                    server.send_command(COMMAND.SWITCH_CAMERA.to_bytes(1))
                    video_stream.switch()
                elif button == DS4_DIGITAL.SQUARE:
                    server.send_command(COMMAND.TOGGLE_NEON.to_bytes(1))
                elif button == DS4_DIGITAL.X:
                    server.send_command(COMMAND.TOGGLE_CLACSON.to_bytes(1))

            elif event.type == pygame.JOYBUTTONUP:
                if button == DS4_DIGITAL.X:
                    server.send_command(COMMAND.TOGGLE_CLACSON.to_bytes(1))

            elif event.type == pygame.JOYAXISMOTION:
                level = event.value
                analog_control = DS4_ANALOG(event.axis)

                direction = None
                intensity = None
                if analog_control == DS4_ANALOG.R2:
                    direction = COMMAND.FORWARD
                    intensity = calculate_march_intensity(level)
                elif analog_control == DS4_ANALOG.L2:
                    direction = COMMAND.BACKWARD 
                    intensity = calculate_march_intensity(level)
                elif analog_control == DS4_ANALOG.L_X:
                    direction = COMMAND.LEFT if level < 0 else COMMAND.RIGHT
                    intensity = calculate_steer_intensity(level)

                if direction is not None and intensity is not None and should_send(direction, intensity):
                    command = direction + intensity
                    server.send_command(command.to_bytes(1))
                    #print(f"Sent {direction.name} {intensity}/{COMMAND_INTENSITY_MAX - 1} - {command}")

            elif event.type == pygame.JOYDEVICEADDED:
                joystick = pygame.joystick.Joystick(event.device_index)
                print(f"{joystick.get_name()} connencted")

            elif event.type == pygame.JOYDEVICEREMOVED:
                print(f"{joystick.get_name()} disconnected")
                joystick = None
        
        if not has_focus:
            colors = [(255, 255, 255), (0,0,0)]
            index = int(time.time()) % 2
            screen.fill(colors[index])
        else:
            screen.fill((255, 255, 255))

        text_surface = PYGAME_FONT.render(f"{max_len * " "} LAST  MAX", True, (0,0,0))
        screen.blit(text_surface, (50, 30))

        for index, metric in enumerate(TEMP_METRICS):
            draw_temp(screen, metric, (50, index*30 + 60))

        pygame.display.flip() # Update the screen
        clock.tick(FPS)
        
if __name__ == "__main__":

    if False:
        import subprocess
        applescript = '''
        tell application "iTerm2"
            tell current window
                set bounds to {1058, 600, 1440, 900} -- {left, top, right, bottom}
            end tell
        end tell
        '''
        subprocess.run(["osascript", "-e", applescript])

    pygame.init()

    normal = "mx437ibmdosiso8"
    bold = "mx437ibmvga8x16"
    PYGAME_FONT = pygame.font.SysFont(bold, 28)

    gamepad_viewer = Gamepad_Viewer()
    gamepad_viewer.start_mirroring()

    gps_tracker = GPS_Tracker()
    gps_tracker.open_live_map()

    network_manager = Network_Manager()
    network_manager.start_monitoring()

    server = Server(telemetry_callback)
    server.start()

    metrics_queue = multiprocessing.Queue()
    video_stream = Stream_Manager(metrics_queue)
    video_stream.play()

    try:
        ui_loop() # Blocking
    except KeyboardInterrupt:
        pass

    gamepad_viewer.stop_mirroring()
    gps_tracker.close_live_map()
    network_manager.stop_monitoring()
    video_stream.close()
    pygame.quit()

    if False:
        applescript = '''
        tell application "iTerm2"
            tell current window
                set bounds to {0, 0, 1440, 900} -- {left, top, right, bottom}
            end tell
        end tell
        '''
        subprocess.run(["osascript", "-e", applescript])

    print("Done")
