import socket
import threading
import struct
from enum import IntEnum
from printer import perror

class METRIC(IntEnum):
    MODEM_TEMP = 3                      # celsius | int
    CAMERA_TEMP = 5                     # celsius | int
    CPU_TEMP = 6                        # celsius | int (Average temp of the high performance core cluster)
    GPU_TEMP = 12                       # celsius | int
    BATTERY_TEMP = 42                   # celsius | int
    PHONE_BATTERY_PERCENT = 100         # [0-100] | int
    POSITION = 101                      # LATITUDE | float, LONGITUDE | float, ACCURACY | int
    HEADING = 102                       # degrees | int
    SIGNAL_LEVEL = 103                  # [0-5] | int
    CAR_BATTERY_VOLTAGE = 104           # centiVolt | int
    ELECTRONICS_BATTERY_VOLTAGE = 105   # centiVolt | int

# Metrics that are displayed on the video stream
STREAM_METRICS = [
    METRIC.PHONE_BATTERY_PERCENT, 
    METRIC.HEADING, 
    METRIC.SIGNAL_LEVEL, 
    METRIC.CAR_BATTERY_VOLTAGE,
    METRIC.ELECTRONICS_BATTERY_VOLTAGE
]
TEMP_METRICS = [
    METRIC.MODEM_TEMP, 
    METRIC.CAMERA_TEMP, 
    METRIC.CPU_TEMP, 
    METRIC.GPU_TEMP, 
    METRIC.BATTERY_TEMP
]

class Server:
    def __init__(self, telemetry_callback):
        self.host = '0.0.0.0'
        self.control_port = 8003
        self.control_socket = None
        self.control_client = None
        self.telemetry_callback = telemetry_callback
        self.running = False

    def start_control_server(self):
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.control_socket.bind((self.host, self.control_port))
            self.control_socket.listen(1)
            print(f"CONTROL SERVER thread listening on TCP {self.host}:{self.control_port}")
        except Exception as e:
            perror(f"Failed to start the control server: {e}")

        # Control socket initialized, listen for incoming client connections
        while self.running:
            try:
                self.control_socket.settimeout(1.0)
                client, addr = self.control_socket.accept()
                client.settimeout(1.0)
                self.control_client = client
                print(f"Control client connected from {addr}")
            except socket.timeout:
                continue

            # Connection active, receive telemetry packets
            while self.running:
                try:
                    self._recv_telemetry()
                except socket.timeout:
                    continue
                except Exception as e:
                    perror(f"Control client error: {e}")
                    break

            self.control_client.close()
            self.control_client = None
            print("Control client disconnected")

    def _recv_bytes(self, num_bytes):
        # Helper to receive exact number of bytes
        data = b''
        while len(data) < num_bytes:
            packet = self.control_client.recv(num_bytes - len(data))
            if not packet:
                raise ConnectionResetError("connection lost")
            data += packet
        return data

    def _recv_telemetry(self):
        metric_byte = self._recv_bytes(1)
        metric = METRIC(metric_byte[0])

        if metric == METRIC.POSITION:
            data = self._recv_bytes(12)
            # Big-endian: 2 floats (lat, lon) and 1 int (accuracy)
            lat, lon, accuracy = struct.unpack('>ffi', data)
            value = (lat, lon, accuracy)
        else:
            data = self._recv_bytes(4)
            value = struct.unpack('>i', data)[0]

        self.telemetry_callback(metric, value)

    def send_command(self, command):
        if not self.running:
            print("The server is not running")
            return
        if not self.control_client:
            print("No control client connected")
            return

        try:
            self.control_client.sendall(command)
        except Exception as e:
            perror(f"Unable to send command: {e}")
            self.control_client.close()
            self.control_client = None
            print("Control client disconnected")

    def stop(self):
        self.running = False
        if self.control_client:
            self.control_client.close()
            self.control_client = None
        if self.control_socket:
            self.control_socket.close()
            self.control_socket = None
        print("CONTROL SERVER thread terminated")

    def start(self):
        self.running = True
        threading.Thread(
            target=self.start_control_server, 
            daemon=True
        ).start()
        print("CONTROL SERVER thread launched")
