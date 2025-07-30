import socket
import threading
import time
import cv2
import numpy as np
from collections import defaultdict
import struct

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
        
        # Video stream processing
        self.frame_buffer = defaultdict(dict)  # {frame_id: {packet_index: data}}
        self.frame_lock = threading.Lock()
        
    def process_stream_packet(self, data):
        """Process incoming stream packet and reconstruct frames"""
        try:
            if len(data) < 8:
                # Single packet JPEG frame
                self.display_frame(data)
                return
                
            # Multi-packet frame - extract header
            frame_id = struct.unpack('<I', data[:4])[0]
            packet_index = struct.unpack('<H', data[4:6])[0]
            total_packets = struct.unpack('<H', data[6:8])[0]
            packet_data = data[8:]
            
            with self.frame_lock:
                # Store packet data
                self.frame_buffer[frame_id][packet_index] = packet_data
                
                # Check if we have all packets for this frame
                if len(self.frame_buffer[frame_id]) == total_packets:
                    # Reconstruct frame
                    frame_data = b''
                    for i in range(total_packets):
                        if i in self.frame_buffer[frame_id]:
                            frame_data += self.frame_buffer[frame_id][i]
                    
                    # Remove completed frame from buffer
                    del self.frame_buffer[frame_id]
                    
                    # Display reconstructed frame
                    self.display_frame(frame_data)
                    
                # Clean up old incomplete frames (older than 2 seconds)
                current_time = time.time()
                frames_to_remove = []
                for fid in self.frame_buffer:
                    if current_time - (fid * 0.1) > 2.0:  # Rough timing estimation
                        frames_to_remove.append(fid)
                        
                for fid in frames_to_remove:
                    del self.frame_buffer[fid]
                    
        except Exception as e:
            print(f"Error processing stream packet: {e}")
            
    def display_frame(self, jpeg_data):
        """Display JPEG frame using OpenCV"""
        try:
            # Decode JPEG data
            nparr = np.frombuffer(jpeg_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                # Add frame info overlay
                height, width = frame.shape[:2]
                info_text = f"Frame: {width}x{height} | Size: {len(jpeg_data)} bytes"
                cv2.putText(frame, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                           0.7, (0, 255, 0), 2)
                
                # Display frame
                cv2.imshow('Video Stream', frame)
                
                # Non-blocking key check
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    print("Video window closed by user")
                    self.running = False
            else:
                print(f"Failed to decode JPEG frame ({len(jpeg_data)} bytes)")
                
        except Exception as e:
            print(f"Error displaying frame: {e}")
        
    def start_stream_server(self):
        """Start UDP server to receive stream data"""
        try:
            self.stream_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.stream_socket.bind((self.host, self.stream_port))
            print(f"Stream server listening on UDP {self.host}:{self.stream_port}")
            print("Video window will open when first frame is received")
            print("Press 'q' in video window to quit")
            
            packet_count = 0
            last_stats_time = time.time()
            
            while self.running:
                try:
                    # Set timeout to check running flag periodically
                    self.stream_socket.settimeout(1.0)
                    data, addr = self.stream_socket.recvfrom(65536)
                    
                    packet_count += 1
                    current_time = time.time()
                    
                    # Process the packet
                    self.process_stream_packet(data)
                    
                    # Print stats every 5 seconds
                    if current_time - last_stats_time >= 5.0:
                        packets_per_sec = packet_count / (current_time - last_stats_time)
                        print(f"Receiving {packets_per_sec:.1f} packets/sec from {addr}")
                        packet_count = 0
                        last_stats_time = current_time
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        print(f"Stream server error: {e}")
                    break
                    
        except Exception as e:
            print(f"Failed to start stream server: {e}")
        finally:
            cv2.destroyAllWindows()
            
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
        
        # Close OpenCV windows
        cv2.destroyAllWindows()
        
        # Close client connections
        for client in [self.telemetry_client, self.control_client]:
            if client:
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
        print("\nServer running. Commands:")
        print("- Press Enter to send a dummy command")
        print("- Press 'q' in video window to quit")
        print("- Press Ctrl+C to stop server")
        
        while server.running:
            try:
                input("Press enter to send a dummy command (or Ctrl+C to quit): ")
                if server.control_client:
                    command = f"CMD.DUMMY\n"
                    server.control_client.send(command.encode('utf-8'))
                    print("Command sent")
                else:
                    print("No control client connected")
            except EOFError:
                # Handle Ctrl+C gracefully
                break
        
    except KeyboardInterrupt:
        pass
    finally:
        print("\nShutting down the server...")
        server.stop()