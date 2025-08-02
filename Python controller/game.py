
import pygame
from enum import Enum

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

FPS = 30
DEADZONE = 0.05

pygame.init()

def main():    
    screen = pygame.display.set_mode((500, 700), pygame.RESIZABLE)
    pygame.display.set_caption("RC++")
    clock = pygame.time.Clock()

    joystick = None
    running = True
    while running:

        for event in pygame.event.get():
            
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.JOYBUTTONDOWN:
                print(f"Button {DS4_DIGITAL(event.button).name} pressed")

            elif event.type == pygame.JOYBUTTONUP:
                print(f"Button {DS4_DIGITAL(event.button).name} released")

            elif event.type == pygame.JOYAXISMOTION:
                for analog_control in DS4_ANALOG:
                    level = joystick.get_axis(analog_control.value)
                    #if abs(level) < DEADZONE:
                    #    continue
                    #if analog_control == DS4_ANALOG.L2 or analog_control == DS4_ANALOG.R2:
                    #    if abs(level) > 1 - DEADZONE:
                    #        continue
                    print(f"Analog {analog_control.name} moved at {level}")

            elif event.type == pygame.JOYDEVICEADDED:
                joystick = pygame.joystick.Joystick(event.device_index)
                print(f"Joystick {joystick.get_name()} connencted")

            elif event.type == pygame.JOYDEVICEREMOVED:
                print(f"Joystick {joystick.get_name()} disconnected")
                joystick = None

        pygame.display.flip() # Update the screen
        clock.tick(FPS)

if __name__ == "__main__":
    main()
    pygame.quit()
