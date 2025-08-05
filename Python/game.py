import os
os.environ['SDL_VIDEO_WINDOW_POS'] = "0,0"

import pygame
import serial
from enum import Enum, IntEnum

from server import ControllerServer

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

class DIRECTION(IntEnum):
	FORWARD = 0
	BACKWARDS = 1
	RIGHT = 2
	LEFT = 3

FPS = 10
STICK_DEADZONE = 0.05
TRIGGER_DEADZONE = 0.01

# State tracking for bandwidth optimization
last_sent_states = {
    DS4_ANALOG.L2: None,
    DS4_ANALOG.R2: None,
    DS4_ANALOG.L_X: None
}

#try:
#    ser = serial.Serial('/dev/cu.usbmodem111201', 115200, timeout=1)
#except serial.SerialException as e:
#    print(f"Could not open serial port: {e}")
#    exit(1)

pygame.init()
controllerServer = ControllerServer()

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

def should_send_command(analog_control, command, direction, speed):
    current_state = (command, direction, speed)
    if last_sent_states[analog_control] == current_state:
        return False
    last_sent_states[analog_control] = current_state
    return True

def main():
    screen = pygame.display.set_mode((765, 900), pygame.NOFRAME)
    pygame.display.set_caption("RC++")
    clock = pygame.time.Clock()

    joystick = None
    while True:

        for event in pygame.event.get():
            
            if event.type == pygame.JOYBUTTONDOWN:
                if DS4_DIGITAL(event.button) == DS4_DIGITAL.TOUCHPAD:
                    return
                #print(f"Button {DS4_DIGITAL(event.button).name} pressed")

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
                    controllerServer.send_command(packet)
                    #ser.write(packet)
                    print(f"[DEBUG] Sent: cmd={command.name}, dir={direction.name}, speed={speed:.2f} (level={level:.2f})")

            elif event.type == pygame.JOYDEVICEADDED:
                joystick = pygame.joystick.Joystick(event.device_index)
                print(f"Joystick {joystick.get_name()} connencted")

            elif event.type == pygame.JOYDEVICEREMOVED:
                print(f"Joystick {joystick.get_name()} disconnected")
                joystick = None
        
        pygame.display.flip() # Update the screen
        clock.tick(FPS)
        

if __name__ == "__main__":
    # write touchpad to quit
    controllerServer.start()
    main() # Blocking

    pygame.quit()
    print("Server stopped")
    