
import os
os.environ['SDL_VIDEO_WINDOW_POS'] = "0,0"

import multiprocessing
import pygame
from enum import Enum, IntEnum
import time

from server import METRIC, STREAM_METRICS, TEMP_METRICS, Server
from map_builder import Map_Builder
from stream_manager import Stream_Manager
from printer import perror
from gamepad_viewer import Gamepad_Viewer

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
    MARCH = 0
    STEER = 1
    SWITCH_CAMERA = 2

class DIRECTION(IntEnum):
	FORWARD = 0
	BACKWARDS = 1
	RIGHT = 2
	LEFT = 3

FPS = 30
STICK_DEADZONE = 0.05
TRIGGER_DEADZONE = 0.01

red_limit = {
    METRIC.MODEM_TEMP: 60,
    METRIC.CAMERA_TEMP: 60,
    METRIC.CPU_TEMP: 70,
    METRIC.GPU_TEMP: 70,
    METRIC.BATTERY_TEMP: 50,
}
orange_limit = {
    METRIC.MODEM_TEMP: 45,
    METRIC.CAMERA_TEMP: 45,
    METRIC.CPU_TEMP: 55,
    METRIC.GPU_TEMP: 55,
    METRIC.BATTERY_TEMP: 40,
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
        color = (0, 200, 0)
    text_surface = PYGAME_FONT.render(text, True, color)
    surface.blit(text_surface, position)

def telemetry_callback(metric, value):
    if metric == METRIC.POSITION:
        map_builder.add_waypoint(value[0], value[1], value[2])
    elif metric in STREAM_METRICS:
        metrics_queue.put_nowait((metric, value))
    elif metric in TEMP_METRICS:
        last_temps[metric] = value
        if max_temps[metric] < value:
            max_temps[metric] = value
    else:
        perror(f"Unhandled metric {metric.name}: {value}")

def calculate_march_speed(level):
    if level < -1 + TRIGGER_DEADZONE:
        return 0
    if level > 1 - TRIGGER_DEADZONE:
        return 255
    return int(((level + 1)/2) * 127 + 128)

def calculate_steer_speed(level):
    if abs(level) < STICK_DEADZONE:
        return 0
    if abs(level) > 1 - STICK_DEADZONE:
        return 255
    return int((abs(level)) * 127 + 128)

# State tracking for bandwidth optimization
last_sent_states = {
    DS4_ANALOG.L2: None,
    DS4_ANALOG.R2: None,
    DS4_ANALOG.L_X: None
}
def should_send_command(analog_control, command, direction, speed):
    current_state = (command, direction, speed)
    if last_sent_states[analog_control] == current_state:
        return False
    last_sent_states[analog_control] = current_state
    return True


def ui_loop():
    screen = pygame.display.set_mode((382, 240), pygame.NOFRAME)
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
                    print(f"Button {DS4_DIGITAL(event.button).name} pressed")
                    server.send_command(COMMAND.SWITCH_CAMERA.to_bytes(1))
                    video_stream.switch()

            #elif event.type == pygame.JOYBUTTONUP:
                #print(f"Button {DS4_DIGITAL(event.button).name} released")

            elif event.type == pygame.JOYAXISMOTION:
                level = event.value
                analog_control = DS4_ANALOG(event.axis)

                command = None
                direction = None
                speed = 0

                if analog_control == DS4_ANALOG.R2:
                    command = COMMAND.MARCH
                    direction = DIRECTION.FORWARD
                    speed = calculate_march_speed(level)
                
                elif analog_control == DS4_ANALOG.L2:
                    command = COMMAND.MARCH
                    direction = DIRECTION.BACKWARDS
                    speed = calculate_march_speed(level)

                elif analog_control == DS4_ANALOG.L_X:
                    command = COMMAND.STEER
                    direction = DIRECTION.LEFT if level < 0 else DIRECTION.RIGHT
                    speed = calculate_steer_speed(level)

                if command is not None and should_send_command(analog_control, command, direction, speed):
                    packet = bytes([command, direction, speed])
                    server.send_command(packet)
                    #print(f"[DEBUG] Sent: cmd={command.name}, dir={direction.name}, speed={speed:.2f} (level={level:.2f})")

            elif event.type == pygame.JOYDEVICEADDED:
                joystick = pygame.joystick.Joystick(event.device_index)
                print(f"Joystick {joystick.get_name()} connencted")

            elif event.type == pygame.JOYDEVICEREMOVED:
                print(f"Joystick {joystick.get_name()} disconnected")
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

    import subprocess

    applescript = '''
    tell application "iTerm2"
        tell current window
            set bounds to {1058, 300, 1440, 900} -- {left, top, right, bottom}
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", applescript])

    pygame.init()

    normal = "mx437ibmdosiso8"
    bold = "mx437ibmvga8x16"
    PYGAME_FONT = pygame.font.SysFont(bold, 28)

    gamepad_viewer = Gamepad_Viewer()
    gamepad_viewer.open_live_view()

    map_builder = Map_Builder()
    map_builder.open_live_map()

    server = Server(telemetry_callback)
    server.start()

    metrics_queue = multiprocessing.Queue()
    video_stream = Stream_Manager(metrics_queue)
    video_stream.play()

    ui_loop() # Blocking

    gamepad_viewer.close_live_view()
    map_builder.close_live_map()
    video_stream.close()
    pygame.quit()

    applescript = '''
    tell application "iTerm2"
        tell current window
            set bounds to {0, 0, 1440, 900} -- {left, top, right, bottom}
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", applescript])

    print("Done")
