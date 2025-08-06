
import folium
from datetime import datetime

class MapBuilder:

    def __init__(self):
        self.FILENAME = "map.html"
        self.PROVIDER = "OpenStreetMap"

        self.last_marker = None
        self.waypoints = []
        self.map = folium.Map(
            location=[45.4642, 9.1900], # Milan as default center
            zoom_start=17,
            tiles=self.PROVIDER
        )
        self.map.save(self.FILENAME)
        
    def add_waypoint(self, lat, lon, accuracy=None):
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            print(f"Invalid coordinates: lat={lat}, lon={lon}")
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
        if accuracy is not None:
            popup_text += f"<br>Accuracy: {accuracy}m"
        
        marker = folium.Marker(
            [lat, lon],
            popup=popup_text,
            tooltip=f"Waypoint #{idx+1}",
            icon=folium.Icon(color=color, icon=icon_name)
        ).add_to(self.map)
                
        # Add the accuracy circle (if available)
        if accuracy is not None and accuracy > 0:
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
        self.map.save(self.FILENAME)
