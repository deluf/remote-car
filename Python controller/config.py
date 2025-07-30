
BAUD_RATE = 1000000
SQUARE_IMAGE_SIDE_LENGTH = 128
TRANSMITTER_SERIAL = "/dev/cu.usbmodem11401"
RECEIVER_SERIAL = "/dev/cu.usbserial-11120"

COMPRESSION = None # Alternatives: None, "MJPEG"

PHY_BLOCK_SIZE = 32
START_SEQUENCE = bytearray([i for i in range(PHY_BLOCK_SIZE)])
END_SEQUENCE = bytearray([PHY_BLOCK_SIZE - i for i in range(PHY_BLOCK_SIZE)])
