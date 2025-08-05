
import socket
import threading

class ControllerServer:
    def __init__(self):
        self.host = '0.0.0.0'
        self.telemetry_port = 8003
        self.control_port = 8004 
        
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
            msg = command + b"\n"
            msglen = len(msg)
            totalsent = 0
            while totalsent < msglen:
                sent = self.control_client.send(msg[totalsent:])
                print(f"[DEBUG] sent={sent}")
                if sent == 0:
                    raise ConnectionResetError()
                totalsent = totalsent + sent
                print("Command sent")
            print(f"Sent {command}")
        except (BrokenPipeError, ConnectionResetError):
            if self.control_client:    
                self.control_client.close()
                self.control_client = None
            print("Control client disconnected")
        except Exception as e:
            print(f"Unable to send command: {e}")
    
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
