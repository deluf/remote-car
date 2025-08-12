
import socket
import threading
import struct
from enum import IntEnum

from printer import perror

class METRIC(IntEnum):
    MODEM_TEMP = 3                      # celsius   | int
    CAMERA_TEMP = 5                     # celsius   | int
    CPU_TEMP = 6                        # celsius   | int  (Average temp of the high performance core cluster)
    GPU_TEMP = 12                       # celsius   | int
    BATTERY_TEMP = 42                   # celsius   | int
    PHONE_BATTERY_PERCENT = 100         # [0-100]   | int
    POSITION = 101                      # LATITUDE  | float,
                                        # LONGITUDE | float,
                                        # ACCURACY  | int
    HEADING = 102                       # degrees   | int
    SIGNAL_LEVEL = 103                  # [0-5]     | int
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
            print(f"Control server listening on TCP {self.host}:{self.control_port}")
        except Exception as e:
            perror(f"Failed to start the control server: {e}")
        
        # Control socket initialized, check forever for incoming connections to accept
        while self.running:
            try:
                # Set a timeout to check the running flag periodically
                self.control_socket.settimeout(1.0)
                client, addr = self.control_socket.accept()
                client.settimeout(1.0)
                self.control_client = client
                print(f"Control client connected from {addr}")
            except socket.timeout:
                continue # No one is connecting (expected, just loop again)

            # Client succesfully connected, check forever for incoming messages to decode
            while self.running:
                try:
                    self._recv_telemetry()
                except socket.timeout:
                    # The client simply is not sending anything (expected, just loop again)
                    continue
                except Exception as e:
                    perror(f"Control client error: {e}")
                    break
            
            # Connection broke - either gracefully or not
            self.control_client.close()
            self.control_client = None
            print("Control client disconnected")

    def _recv_telemetry(self):
        # The first byte identifies the metric type
        packet = self.control_client.recv(1)
        if not packet:
            raise ConnectionResetError("connection lost")
        metric = METRIC(packet[0])
        
        # Next, each metric encodes its values in 4-bytes numbers
        # Every metric except for position uses one 4-byte integer
        # Position uses three 4-byte floats
        data = b''
        expected_bytes = 4
        if metric == METRIC.POSITION:
            expected_bytes *= 3

        while len(data) < expected_bytes:
            packet = self.control_client.recv(expected_bytes - len(data))
            if not packet:
                raise ConnectionResetError("connection lost")
            data += packet
        
        if metric == METRIC.POSITION:
            value = []
            value.append(struct.unpack('>f', data[:4])[0])  # big-endian float
            value.append(struct.unpack('>f', data[4:8])[0]) # big-endian float
            value.append(struct.unpack('>i', data[8:])[0])  # big-endian int
        else:
            value = struct.unpack('>i', data)[0] # big-endian int

        # Consume the decoded data
        self.telemetry_callback(metric, value)

    def send_command(self, command):
        # There might be race conditions because self.control_client
        #  is used both here and by the listening deamon
        if not self.running:
            print("The server is not running")
            return
        if not self.control_client: 
            print("No control client connected")
            return
    
        try:
            msglen = len(command)
            totalsent = 0
            while totalsent < msglen:
                sent = self.control_client.send(command[totalsent:])
                if sent == 0:
                    raise ConnectionResetError("connection lost")
                totalsent = totalsent + sent
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
                    
        print("Server stopped")

    def start(self):
        self.running = True
        threading.Thread(
           target=self.start_control_server, 
           daemon=True
        ).start()
