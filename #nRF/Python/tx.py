
from PIL import Image       # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import numpy as np          # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import serial               # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import cv2                  # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from io import BytesIO
from time import time, sleep
from config import *

bandwidth_savings = []
uncompressed_frame_size = SQUARE_IMAGE_SIDE_LENGTH * SQUARE_IMAGE_SIDE_LENGTH

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

    if COMPRESSION == "MJPEG":
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        bandwidth_savings.append((1 - len(buffer.getvalue()) / uncompressed_frame_size) * 100)
        return buffer.getvalue()
    
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

bytes_sent = 0

# Open the serial connection
frames_sent = 0
with serial.Serial(TRANSMITTER_SERIAL, BAUD_RATE, rtscts=True) as ser:
    sleep(3)

    start_time = time()
    while(True):    
        elapsed_time = time() - start_time        
        next_frame_index = round(elapsed_time * fps)
        if next_frame_index >= len(preloaded_frames):
            break
        frames_sent += 1
        
        frame_bytes = preloaded_frames[next_frame_index]
        ser.write(START_SEQUENCE)
        ser.write(len(frame_bytes).to_bytes(4, byteorder='big'))
        ser.write(frame_bytes)

        bytes_sent += PHY_BLOCK_SIZE + 4 + len(frame_bytes)
        
    ser.write(END_SEQUENCE)
    ser.flush()

    print(f"Total elapsed time: {time() - start_time:.2f}")
    print(f"Dropped {(frame_count - frames_sent) / frame_count * 100:.2f}% of the frames")
    print(f"Maximum theoretical bandwidth: {BAUD_RATE * 0.8 / 1000:.2f} Kbps")
    print(f"Achieved bandwidth: {bytes_sent * 8 / 1000 / (time() - start_time):.2f} Kbps")
    if COMPRESSION == "MJPEG":
        print(f"{COMPRESSION} compression saved around {np.mean(bandwidth_savings):.2f}% of the bandwidth")
