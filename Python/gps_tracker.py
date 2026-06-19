import shutil
import subprocess
from pathlib import Path
from datetime import datetime
import folium
import psutil
from printer import perror, monitor_stderr

if not shutil.which("npx"):
    perror("npx is not installed or not found in PATH")

MAP_PATH = Path.cwd() / "gps_tracker" / "map.html"

class GPSTracker:
    def __init__(self):
        self.process = None
        self.last_marker = None
        self.waypoints = []
        self.map = folium.Map(
            location=[45.4642, 9.1900], # Milan as default center
            zoom_start=17,
            tiles="OpenStreetMap"
        )
        self.map.save(MAP_PATH)

    def add_waypoint(self, lat, lon, accuracy):
        # Accuracy can be 0, meaning that it was not possible to measure it
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180) or accuracy < 0:
            perror(f"Invalid coordinates: lat={lat}, lon={lon}, accuracy={accuracy}")
            return

        timestamp = datetime.now()
        new_waypoint = {
            'lat': lat,
            'lon': lon,
            'accuracy': accuracy,
            'timestamp': timestamp
        }
        self.waypoints.append(new_waypoint)

        idx = len(self.waypoints) - 1
        color = 'green' if idx == 0 else 'red'
        icon_name = 'play' if idx == 0 else 'stop'

        # Add the waypoint marker to the map
        popup_text = f"Point {idx+1}<br>Lat: {lat:.6f}<br>Lon: {lon:.6f}<br>Time: {timestamp.strftime('%H:%M:%S')}"
        if accuracy > 0:
            popup_text += f"<br>Accuracy: {accuracy}m"

        marker = folium.Marker(
            [lat, lon],
            popup=popup_text,
            tooltip=f"Waypoint #{idx+1}",
            icon=folium.Icon(color=color, icon=icon_name)
        ).add_to(self.map)

        # Add the accuracy circle if available
        if accuracy > 0:
            folium.Circle(
                location=[lat, lon],
                radius=accuracy,
                color='black',
                fill=True,
                fillOpacity=0.2,
                weight=1
            ).add_to(self.map)

        # Center the map around the new waypoint
        self.map.location = [lat, lon]

        # If the added waypoint is the first, save map and return
        if self.last_marker is None:
            self.last_marker = marker
            self.map.save(MAP_PATH)
            return

        # Get the previous waypoint to draw a connection line
        prev_idx = idx - 1
        prev_wp = self.waypoints[prev_idx]

        folium.PolyLine(
            [[prev_wp['lat'], prev_wp['lon']], [lat, lon]],
            color='red',
            weight=3,
            opacity=0.8,
        ).add_to(self.map)

        # Change previous marker's icon if it was not the first waypoint
        if prev_idx > 0:
            self.last_marker.set_icon(folium.Icon(color='blue', icon='record'))

        self.last_marker = marker
        self.map.save(MAP_PATH)

    def open_live_map(self):
        # Start Electron GPS tracker in the background
        try:
            self.process = subprocess.Popen(["npx", "electron", "gps_tracker"], stderr=subprocess.PIPE)
            monitor_stderr(self.process, "GPS TRACKER")
            print("GPS TRACKER process launched")
        except Exception as e:
            perror(f"Failed to launch GPS TRACKER: {e}")

    def close_live_map(self):
        # Kill Electron process and its child processes
        if not self.process:
            print("No GPS TRACKER process to terminate")
            return

        try:
            parent = psutil.Process(self.process.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
            print("GPS TRACKER process terminated")
        except psutil.NoSuchProcess:
            print("GPS TRACKER process already dead")
        finally:
            self.process = None
