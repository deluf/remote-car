
import shutil
from printer import perror
if shutil.which("npx") is None:
    perror("npx is not installed or not found in PATH")

import folium
import psutil
import subprocess
from pathlib import Path
from datetime import datetime

from printer import monitor_stderr

MAP_PATH = Path.cwd() / "gps_tracker" / "map.html"

class GPS_Tracker:

    def __init__(self):
        self.background_process = None

        self.last_marker = None
        self.waypoints = []
        self.map = folium.Map(
            location=[45.4642, 9.1900], # Milan as default center
            zoom_start=17,
            tiles="OpenStreetMap"
        )
        self.map.save(MAP_PATH)
        
    def add_waypoint(self, lat, lon, accuracy):
        # Accuracy can be 0, meaning that it wasn't possible to measure it
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180) or not (accuracy >= 0):
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
        
        # If the waypoint is the first, then mark it differently
        idx = len(self.waypoints) - 1
        if idx == 0:
            color = 'green'
            icon_name = 'play'
        else:
            color = 'red'
            icon_name = 'stop'

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
                
        # Add the accuracy circle (if available)
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

        # If the added waypoint is the first, stop here
        if self.last_marker is None:
            self.last_marker = marker
            self.map.save(MAP_PATH)
            return

        # Get the old latest waypoint
        last_idx = idx - 1
        last_waypoint = self.waypoints[last_idx]
        last_lat, last_lon = last_waypoint['lat'], last_waypoint['lon']

        # Add line connecting the latest and new waypoints
        folium.PolyLine(
            [[last_lat, last_lon], [lat, lon]],
            color='red',
            weight=3,
            opacity=0.8,
        ).add_to(self.map)

        # If the latest waypoint wasn't the first, change its icon
        if (last_idx > 0):
            self.last_marker.set_icon(folium.Icon(color='blue', icon='record'))
        
        self.last_marker = marker
        self.map.save(MAP_PATH)

    def open_live_map(self):
        cmd = ["npx", "electron", "gps_tracker"]
        try:
            self.background_process = subprocess.Popen(cmd, stderr=subprocess.PIPE)
            monitor_stderr(self.background_process, "GPS TRACKER")
            print("GPS TRACKER process launched")
        except Exception as e:
            perror(f"Failed to launch GPS TRACKER: {e}")

    def close_live_map(self):
        if self.background_process:
            parent = psutil.Process(self.background_process.pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
            print("GPS TRACKER process terminated")
        else:
            print("No GPS TRACKER process to terminate")
