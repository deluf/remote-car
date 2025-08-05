
from PIL import Image       # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import serial                   # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import numpy as np              # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import matplotlib.pyplot as plt # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import matplotlib.patheffects   # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from io import BytesIO
from time import time
from config import *

image_size = (SQUARE_IMAGE_SIDE_LENGTH, SQUARE_IMAGE_SIDE_LENGTH)
max_bytes_per_frame = image_size[0] * image_size[1]
image_buffer = np.zeros(max_bytes_per_frame, dtype=np.uint8)

plt.ion()
plt.rc('font', family='serif')
fig, ax = plt.subplots(figsize=(5, 5))
img_display = ax.imshow(np.zeros(image_size), cmap='gray', vmin=0, vmax=255)
ax.axis('off')
fps_text = ax.text(
    0.75, 0.05, "", transform=ax.transAxes,
    fontsize=13, fontweight='bold', fontfamily='Courier New', 
    ha="center", va="center",
    color='white', path_effects=[ matplotlib.patheffects.withStroke(linewidth=2, foreground='black') ]
)
bandwidth_text = ax.text(
    0.25, 0.05, "", transform=ax.transAxes,
    fontsize=13, fontweight='bold', fontfamily='Courier New',
    ha="center", va="center",
    color='white', path_effects=[ matplotlib.patheffects.withStroke(linewidth=2, foreground='black') ]
)
ax.set_title(
    f"Streaming at {SQUARE_IMAGE_SIDE_LENGTH}x{SQUARE_IMAGE_SIDE_LENGTH} [grayscale, {"lossless" if COMPRESSION == None else COMPRESSION}]",
    fontsize=13, pad=10
)
plt.show()

def wait_for_start_sequence(ser):
    sync_byte_index = 0
    while sync_byte_index < PHY_BLOCK_SIZE:
        byte = int.from_bytes(ser.read())
        if byte == START_SEQUENCE[sync_byte_index]:
            sync_byte_index += 1
        elif byte == START_SEQUENCE[0]:
            sync_byte_index = 1
        else:
            sync_byte_index = 0
    
    length_bytes = ser.read(4)
    return int.from_bytes(length_bytes, byteorder='big')

frame_sizes = []
frame_times_ms = []

def update_stats(frame_size, frame_time_ms):
    frame_sizes.append(frame_size)
    frame_times_ms.append(frame_time_ms)

    mean_frame_time_recent_ms = np.mean(frame_times_ms[-10:])
    mean_bandwidth_recent_Kbps = np.mean(frame_sizes[-10:]) * 8 / mean_frame_time_recent_ms

    fps_text.set_text(f"{1000 / mean_frame_time_recent_ms:.2f} FPS")
    bandwidth_text.set_text(f"{mean_bandwidth_recent_Kbps:.2f} Kbps")

def stream_frame():
    frame_size = wait_for_start_sequence(ser)
    if COMPRESSION == None:
        frame_size = max_bytes_per_frame
    if frame_size > max_bytes_per_frame:
        print(f"Received unrealistic frame size {frame_size}")
        frame_size = max_bytes_per_frame

    start_time = time()
    i = 0
    while i < frame_size:
        available_bytes = ser.in_waiting
        if available_bytes <= 0:
            continue
        if i + available_bytes >= frame_size:
            available_bytes = frame_size - i
        block = ser.read(available_bytes)
        image_buffer[i:i + available_bytes] = np.frombuffer(block[:available_bytes], dtype=np.uint8)
        i += available_bytes

    # Optionally you can update the plot as soon as data arrives (just tab this section)
    if COMPRESSION == "MJPEG":
        try:
            img = Image.open(BytesIO(image_buffer[:frame_size])).convert("L")
            img_display.set_data(np.array(img))
        except Exception:
            print("Failed to decode JPEG frame")
            return
    else:
        img_display.set_data(image_buffer.reshape(image_size))
    
    fig.canvas.draw_idle()
    fig.canvas.flush_events()

    frame_time_ms = (time() - start_time) * 1000
    update_stats(frame_size, frame_time_ms)

try:
    with serial.Serial(RECEIVER_SERIAL, BAUD_RATE, rtscts=True) as ser:
        while True:
            stream_frame()
except KeyboardInterrupt:
    pass

#plt.ioff()
#plt.show()
#plt.title("Stream stopped")
