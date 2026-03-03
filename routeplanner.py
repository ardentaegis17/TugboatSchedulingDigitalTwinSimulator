import sys
import os
# Force the script to look inside the virtual environment for packages
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.venv', 'Lib', 'site-packages'))

import json
import math
import networkx as nx
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import nearest_points


class RoutePlanner:
    def __init__(self, geojson_path, origin_lat=1.264, origin_lon=103.792):
        """
        origin_lat/lon: The reference point (0,0) in Unity. 
        MUST match the origin used for your Trajectory CSVs.
        """
        self.origin_lat = origin_lat
        self.origin_lon = origin_lon
        self.terminal_poly = self.load_terminal_polygon(geojson_path)
        
        # Create a slightly buffered version (e.g., 50m) so tugs don't scrape the wall
        self.safe_poly = self.terminal_poly.buffer(50) 
        
        # Pre-calculate graph nodes from polygon exterior
        self.nodes = list(self.safe_poly.exterior.coords)

    def latlon_to_unity(self, lon, lat):
        """Simple Equirectangular projection to Meters/Unity Units"""
        R = 6371000 # Earth Radius in meters
        x = (lon - self.origin_lon) * (math.pi / 180) * R * math.cos(self.origin_lat * math.pi / 180)
        z = (lat - self.origin_lat) * (math.pi / 180) * R
        return (x, z)

    def load_terminal_polygon(self, path):
        with open(path, 'r') as f:
            data = json.load(f)
        
        # Extract Coordinates from FeatureCollection 
        coords_raw = data['features'][0]['geometry']['coordinates'][0]
        
        # Convert to Unity Units (Meters)
        coords_unity = [self.latlon_to_unity(lon, lat) for lon, lat in coords_raw]
        return Polygon(coords_unity)

    def get_safe_distance(self, start_pos, end_pos):
        """
        Calculates shortest path distance avoiding the terminal.
        start_pos, end_pos: Tuple (x, z) in Unity Units
        """
        start_pt = Point(start_pos)
        end_pt = Point(end_pos)
        
        # 1. Trivial Check: Line of Sight
        # If straight line doesn't hit the terminal, use Euclidean
        direct_line = LineString([start_pt, end_pt])
        if not direct_line.intersects(self.terminal_poly):
            return direct_line.length
        
        # 2. Pathfinding (Visibility Graph)
        # If blocked, we must route via polygon corners
        graph = nx.Graph()
        
        # Add Start/End to potential nodes
        all_points = [start_pos, end_pos] + self.nodes
        
        # Build Edges (Connect points that can "see" each other)
        # Optimization: Only connect Start/End to all corners, and corners to adjacent corners
        # For a perfect result, we check all-to-all, but it's slow.
        # Fast Heuristic: Connect Start/End to all visible corners
        
        # A. Connect Start to visible nodes
        for node in self.nodes:
            line = LineString([start_pt, Point(node)])
            if not line.crosses(self.terminal_poly): # Use 'crosses' to allow touching boundary
                graph.add_edge("start", node, weight=line.length)
        
        # B. Connect End to visible nodes
        for node in self.nodes:
            line = LineString([end_pt, Point(node)])
            if not line.crosses(self.terminal_poly):
                graph.add_edge("end", node, weight=line.length)

        # C. Connect Perimeter (Corner i to Corner i+1)
        for i in range(len(self.nodes) - 1):
            p1 = self.nodes[i]
            p2 = self.nodes[i+1]
            dist = math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)
            graph.add_edge(p1, p2, weight=dist)

        # 3. Solve Dijkstra
        try:
            path_length = nx.shortest_path_length(graph, source="start", target="end", weight="weight")
            return path_length
        except nx.NetworkXNoPath:
            # Fallback (Should not happen unless start/end are INSIDE the polygon)
            return direct_line.length