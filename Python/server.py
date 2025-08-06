
import socket
import threading
import struct
from enum import IntEnum

class Metric(IntEnum):                       # BANDWIDTH ?
    BATTERY_PERCENT = 0 # [0-100]  | int           ICON + TEXT
    BATTERY_TEMP = 1    # celsius  | int           TEXT - or remove
    POSITION = 2,       # LATITUDE  | float,
                        # LONGITUDE | float,
                        # ACCURACY  | int
    HEADING = 3         # degrees  | int           VIDEO - SLIDER ON TOP LIKE GEOGUESSR
    SIGNAL_LEVEL = 4    # [0-4]    | int           CHART? VIDEO?

class Server:
    def __init__(self, telemetry_callback):
        self.host = '0.0.0.0'
        self.telemetry_port = 8003
        self.control_port = 8004 
        self.telemetry_callback = telemetry_callback
    
        self.telemetry_socket = None  
        self.control_socket = None
        
        self.telemetry_client = None
        self.control_client = None
        
        self.running = True
           
    def start_telemetry_server(self):
        try:
            self.telemetry_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.telemetry_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.telemetry_socket.bind((self.host, self.telemetry_port))
            self.telemetry_socket.listen(1)
            print(f"Telemetry server listening on TCP {self.host}:{self.telemetry_port}")
            
            while self.running:
                try:
                    # Set timeout to check running flag periodically
                    self.telemetry_socket.settimeout(1.0)
                    client, addr = self.telemetry_socket.accept()
                    self.telemetry_client = client
                    print(f"Telemetry client connected from {addr}")
                    
                    # Handle telemetry data
                    while self.running:
                        try:
                            client.settimeout(1.0)

                            # First read the metric byte
                            packet = self.telemetry_client.recv(1)
                            if not packet:
                                break
                            
                            # Raises exception on value error
                            metric = Metric(packet[0])
                            
                            data = b''
                            expected_bytes = 4
                            if metric == Metric.POSITION:
                                expected_bytes *= 3 # We expect three values

                            while len(data) < expected_bytes:
                                packet = self.telemetry_client.recv(expected_bytes - len(data))
                                if not packet:
                                    break
                                data += packet
                            else:
                                self.recv_telemetry(metric, data)
                                continue  # Continue if the inner loop wasn't broken.
                            break

                        except socket.timeout:
                            continue
                        except Exception as e:
                            print(f"Telemetry client error: {e}")
                            break
                            
                    client.close()
                    self.telemetry_client = None
                    print("Telemetry client disconnected")
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Telemetry server error: {e}")
                    break
                    
        except Exception as e:
            print(f"Failed to start telemetry server: {e}")
            
    def start_control_server(self):
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.control_socket.bind((self.host, self.control_port))
            self.control_socket.listen(1)
            print(f"Control server listening on TCP {self.host}:{self.control_port}")
            
            while self.running:
                try:
                    # Set timeout to check running flag periodically
                    self.control_socket.settimeout(1.0)
                    client, addr = self.control_socket.accept()
                    self.control_client = client
                    print(f"Control client connected from {addr}")
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Control server error: {e}")
                    break

        except Exception as e:
            print(f"Failed to start control server: {e}")
        
    def send_command(self, command):
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
                    raise ConnectionResetError()
                #print(f"[DEBUG] sent={command[totalsent:totalsent+sent]}")
                totalsent = totalsent + sent
        except (BrokenPipeError, ConnectionResetError):
            if self.control_client:    
                self.control_client.close()
                self.control_client = None
            print("Control client disconnected")
        except Exception as e:
            print(f"Unable to send command: {e}")
    
    def recv_telemetry(self, metric, data):

        if metric == Metric.POSITION:
            value = []
            value.append(struct.unpack('>f', data[:4])[0])  # big-endian float
            value.append(struct.unpack('>f', data[4:8])[0]) # big-endian float
            value.append(struct.unpack('>i', data[8:])[0])  # big-endian int
        else:
            value = struct.unpack('>i', data)[0] # big-endian int

        self.telemetry_callback(metric, value)

    def stop(self):
        self.running = False
        
        # Close client connections
        for client in [self.telemetry_client, self.control_client]:
            if client:
                try:
                    client.close()
                except:
                    pass
                
        # Close server sockets
        for sock in [self.telemetry_socket, self.control_socket]:
            if sock:
                try:
                    sock.close()
                except:
                    pass
                    
        print("Server stopped")

    def start(self):
        telemetry_thread = threading.Thread(target=self.start_telemetry_server, daemon=True)
        control_thread = threading.Thread(target=self.start_control_server, daemon=True)
        
        telemetry_thread.start()
        control_thread.start()
