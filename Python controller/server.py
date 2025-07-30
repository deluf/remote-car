
import socket
import threading
import time

class ControllerServer:
    def __init__(self, host='0.0.0.0'):
        self.host = host
        self.stream_port = 8001    # UDP for receiving stream data
        self.telemetry_port = 8002 # TCP for receiving telemetry
        self.control_port = 8003   # TCP for sending control commands
        
        # Socket objects
        self.stream_socket = None
        self.telemetry_socket = None  
        self.control_socket = None
        
        # Client connections
        self.telemetry_client = None
        self.control_client = None
        
        # Control flags
        self.running = True
        
    def start_stream_server(self):
        """Start UDP server to receive stream data"""
        try:
            self.stream_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.stream_socket.bind((self.host, self.stream_port))
            print(f"Stream server listening on UDP {self.host}:{self.stream_port}")
            
            while self.running:
                try:
                    # Set timeout to check running flag periodically
                    self.stream_socket.settimeout(1.0)
                    data, addr = self.stream_socket.recvfrom(65536)
                    print(f"Received {len(data)} bytes of stream data from {addr}")
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Stream server error: {e}")
                    break
                    
        except Exception as e:
            print(f"Failed to start stream server: {e}")
            
    def start_telemetry_server(self):
        """Start TCP server to receive telemetry data"""
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
                            data = client.recv(1024).decode('utf-8').strip()
                            if not data:
                                break
                            print(f"Received telemetry: {data}")
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
        """Start TCP server to send control commands"""
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
            
    def start(self):
        """Start all server threads"""
        print("Starting the controller server...")
        print("Press Ctrl+C to stop")
        
        # Start server threads
        stream_thread = threading.Thread(target=self.start_stream_server, daemon=True)
        telemetry_thread = threading.Thread(target=self.start_telemetry_server, daemon=True)
        control_thread = threading.Thread(target=self.start_control_server, daemon=True)
        
        stream_thread.start()
        telemetry_thread.start()
        control_thread.start()
        
    def stop(self):
        """Stop all servers and close sockets"""
        self.running = False
        
        # Close client connections
        for client in [self.telemetry_client, self.control_client]:
            try:
                client.close()
            except:
                pass
                
        # Close server sockets
        for sock in [self.stream_socket, self.telemetry_socket, self.control_socket]:
            if sock:
                try:
                    sock.close()
                except:
                    pass
                    
        print("Server stopped")


if __name__ == "__main__":
    server = ControllerServer()
    server.start()

    try:
        time.sleep(3)
        while True:
            input("Press enter to send a dummy command")
            try:
                command = f"CMD.DUMMY\n"
                server.control_client.send(command.encode('utf-8'))
            except Exception as e:
                print(f"Error sending control command: {e}")
        
    except KeyboardInterrupt:
        print("\nShutting down the server...")
        server.stop()
    