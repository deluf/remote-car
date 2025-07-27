
import serial                   # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import numpy as np              # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import matplotlib.pyplot as plt # pyright: ignore[reportMissingImports, reportMissingModuleSource]
import matplotlib.patheffects   # pyright: ignore[reportMissingImports, reportMissingModuleSource]
from time import time
import sys
from config import *

# Setup
image_size = (SQUARE_IMAGE_SIDE_LENGTH, SQUARE_IMAGE_SIDE_LENGTH)
total_bytes = image_size[0] * image_size[1]
image_buffer = np.zeros(total_bytes, dtype=np.uint8)

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
    f"Streaming at {SQUARE_IMAGE_SIDE_LENGTH}x{SQUARE_IMAGE_SIDE_LENGTH} [grayscale, lossless]",
    fontsize=13, pad=10
)
plt.show()

frame_times = []

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

def update_stats():
    mean_frame_time_ms = np.mean(frame_times)
    std_frame_times_ms = np.std(frame_times)
    mean_bandwidth_Kbps = total_bytes * 8 / mean_frame_time_ms
    theo_max_bandwidth_Kbps = BAUD_RATE * 0.8 / 1000

    mean_frame_time_recent_ms = np.mean(frame_times[-10:]) if len(frame_times) >= 10 else mean_frame_time_ms
    mean_bandwidth_recent_Kbps = total_bytes * 8 / mean_frame_time_recent_ms

    fps_text.set_text(f"{1000 / mean_frame_time_recent_ms:.2f} FPS")
    bandwidth_text.set_text(f"{mean_bandwidth_recent_Kbps:.2f} Kbps")

    # Move the cursor up 3 lines and clear them
    sys.stdout.write("\033[F\033[K" * 3)  # ANSI escape: \033[F moves up, \033[K clears line
    sys.stdout.write(f"Frame time: {mean_frame_time_ms:.2f} +/- {std_frame_times_ms:.2f} ms\n")
    sys.stdout.write(f"Maximum theoretical bandwidth: {theo_max_bandwidth_Kbps:.2f} Kbps\n")
    sys.stdout.write(f"Measured bandwidth: {mean_bandwidth_Kbps:.2f} Kbps, {mean_bandwidth_Kbps / theo_max_bandwidth_Kbps * 100:.2f}% of the maximum\n")
    sys.stdout.flush()

def stream_frame():
    wait_for_start_sequence(ser)

    start_time = time()
    i = 0
    while i < total_bytes:
        available_bytes = ser.in_waiting
        if available_bytes <= 0:
            continue
        if i + available_bytes >= total_bytes:
            available_bytes = total_bytes - i
        block = ser.read(available_bytes)
        image_buffer[i:i + available_bytes] = np.frombuffer(block[:available_bytes], dtype=np.uint8)
        i += available_bytes

        image_array = image_buffer.reshape(image_size)
        img_display.set_data(image_array)
        fig.canvas.draw_idle()
        fig.canvas.flush_events()

    elapsed_time = time() - start_time
    frame_times.append(elapsed_time * 1000)
    update_stats()

try:
    with serial.Serial(RECEIVER_SERIAL, BAUD_RATE, rtscts=True) as ser:
        while True:
            stream_frame()
except KeyboardInterrupt:
    pass

#plt.ioff()
#plt.show()
#plt.title("Stream stopped")
