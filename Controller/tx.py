
from PIL import Image
import numpy as np
import serial
import cv2
from time import time, sleep

from config import *
SERIAL_PORT = "/dev/cu.usbmodem11401"

def process_frame(frame):
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    # Convert to 1:1 aspect ratio
    width, height = img.size
    if (width != height):
        min_dim = min(width, height)
        left = (width - min_dim) // 2
        top = (height - min_dim) // 2
        right = left + min_dim
        bottom = top + min_dim
        img = img.crop((left, top, right, bottom))

    img = img.resize((SQUARE_IMAGE_SIDE_LENGTH, SQUARE_IMAGE_SIDE_LENGTH), Image.LANCZOS)
    img = img.convert("L")
    
    return np.array(img).flatten()


# Preload the frames
cap = cv2.VideoCapture("video.mp4")
fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
preloaded_frames = []

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break
    image_bytes = process_frame(frame)
    preloaded_frames.append(image_bytes)

cap.release()
print(f"Preloaded {len(preloaded_frames)} frames")

# Open the serial connection
frames_sent = 0
with serial.Serial(SERIAL_PORT, BAUD_RATE, rtscts=True) as ser:
    sleep(3)  # Wait for the microcontroller to reboot

    start_time = time()
    while(True):    
        elapsed_time = time() - start_time
        
        next_frame_index = round(elapsed_time * fps)
        if next_frame_index >= len(preloaded_frames):
            break

        frames_sent += 1
        
        frame_bytes = preloaded_frames[next_frame_index]
        ser.write(START_SEQUENCE)
        ser.write(frame_bytes)
        ser.write(END_SEQUENCE)
        ser.flush()

    print(f"Total elapsed time: {time() - start_time:.2f} [Expected {frame_count / fps:.2f}]")
    print(f"Dropped {(frame_count - frames_sent) / frame_count * 100:.2f}% of the frames")

#print(f"Image: {SQUARE_IMAGE_SIDE_LENGTH}x{SQUARE_IMAGE_SIDE_LENGTH} pixels")
#print(f"Payload Size: {len(image_bytes)} bytes")
#print(f"Attempting to transmit via {SERIAL_PORT} at {BAUD_RATE} baud")

# Theoretical ETA assuming the serial connection is the bottleneck
# Assumes a standard 10 bits per byte (1 start, 8 data, 1 stop)
#total_bytes = len(START_SEQUENCE) + len(image_bytes)
#theoretical_eta_s = total_bytes / (BAUD_RATE / 10) 
#print(f"Theoretical ETA: {theoretical_eta_s * 1000:.2f} ms")
#print(f"Theoretical Max FPS: {1 / theoretical_eta_s:.2f}")
