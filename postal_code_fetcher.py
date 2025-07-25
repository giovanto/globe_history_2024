"""
Fetch precise postal code boundaries for Netherlands from official PDOK service
"""
import requests
import geopandas as gpd
from shapely.geometry import Point, Polygon
import json
from typing import Optional, Tuple, List
import os


class PostalCodeFetcher:
    """Fetch Dutch postal code boundaries from PDOK (official government service)"""
    
    def __init__(self):
        """Initialize postal code fetcher"""
        self.pdok_wfs_url = "https://geodata.nationaalgeoregister.nl/cbspostcode4/wfs"
        self.cache_dir = "postal_cache"
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_postcode_boundary(self, postcode: str) -> Optional[gpd.GeoDataFrame]:
        """
        Get precise boundary polygon for Dutch postal code
        
        Args:
            postcode: 4-digit postal code (e.g., "1032")
            
        Returns:
            GeoDataFrame with postal code boundary polygon
        """
        cache_file = os.path.join(self.cache_dir, f"pc4_{postcode}.geojson")
        
        # Check cache first
        if os.path.exists(cache_file):
            print(f"Loading cached boundary for postal code {postcode}")
            return gpd.read_file(cache_file)
        
        # Fetch from PDOK WFS service
        params = {
            'service': 'WFS',
            'version': '2.0.0',
            'request': 'GetFeature',
            'typeName': 'cbspostcode4:cbs_pc4_2021',
            'outputFormat': 'application/json',
            'CQL_FILTER': f"pc4='{postcode}'"
        }
        
        try:
            print(f"Fetching boundary for postal code {postcode} from PDOK...")
            response = requests.get(self.pdok_wfs_url, params=params, timeout=30)
            response.raise_for_status()
            
            geojson_data = response.json()
            
            if not geojson_data.get('features'):
                print(f"No boundary found for postal code {postcode}")
                return None
            
            # Convert to GeoDataFrame
            gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])
            gdf.crs = "EPSG:28992"  # Dutch coordinate system
            gdf = gdf.to_crs("EPSG:4326")  # Convert to WGS84 for compatibility
            
            # Cache the result
            gdf.to_file(cache_file, driver='GeoJSON')
            print(f"✅ Cached boundary for postal code {postcode}")
            
            return gdf
            
        except Exception as e:
            print(f"Error fetching postal code boundary: {e}")
            return None
    
    def get_postcode_center(self, postcode: str) -> Optional[Tuple[float, float]]:
        """Get center coordinates of postal code area"""
        gdf = self.get_postcode_boundary(postcode)
        
        if gdf is None or gdf.empty:
            return None
            
        centroid = gdf.geometry.centroid.iloc[0]
        return (centroid.y, centroid.x)  # lat, lon
    
    def is_point_in_postcode(self, lat: float, lon: float, postcode: str) -> bool:
        """Check if a point is within the postal code boundary"""
        gdf = self.get_postcode_boundary(postcode)
        
        if gdf is None or gdf.empty:
            return False
        
        point = Point(lon, lat)
        return gdf.geometry.contains(point).any()
    
    def get_postcode_info(self, postcode: str) -> dict:
        """Get detailed information about postal code area"""
        gdf = self.get_postcode_boundary(postcode)
        
        if gdf is None or gdf.empty:
            return {"error": f"No data found for postal code {postcode}"}
        
        # Calculate area and bounds
        geom = gdf.geometry.iloc[0]
        bounds = geom.bounds  # (minx, miny, maxx, maxy)
        
        # Convert area to square kilometers (approximate)
        area_deg_sq = geom.area
        # Rough conversion at Amsterdam latitude (52.3°N)
        area_km_sq = area_deg_sq * 111.32 * 111.32 * 0.6157  # cos(52.3°) ≈ 0.6157
        
        return {
            "postcode": postcode,
            "center_lat": geom.centroid.y,
            "center_lon": geom.centroid.x,
            "bounds": {
                "south": bounds[1],
                "west": bounds[0], 
                "north": bounds[3],
                "east": bounds[2]
            },
            "area_km2": round(area_km_sq, 2),
            "geometry": geom
        }


class AmsterdamAreas:
    """Helper class for Amsterdam area analysis"""
    
    def __init__(self):
        self.pc_fetcher = PostalCodeFetcher()
        
        # Schiphol airport coordinates
        self.schiphol_coords = (52.3105, 4.7683)  # lat, lon
        
        # Common Amsterdam Noord postal codes
        self.noord_postcodes = ['1031', '1032', '1033', '1034', '1035', '1036']
    
    def get_schiphol_approach_area(self) -> dict:
        """
        Define broader area for Schiphol approach analysis
        Covers typical approach corridors from north/northeast
        """
        # Extended area covering approach paths to Schiphol
        return {
            "name": "Schiphol Approach Area",
            "bounds": {
                "south": 52.0,   # South of Schiphol
                "west": 4.5,     # West of Amsterdam
                "north": 52.7,   # North of Amsterdam
                "east": 5.2      # East of Amsterdam  
            }
        }
    
    def analyze_postcode_vs_schiphol(self, postcode: str) -> dict:
        """Compare postal code area with Schiphol proximity"""
        pc_info = self.pc_fetcher.get_postcode_info(postcode)
        
        if "error" in pc_info:
            return pc_info
        
        # Calculate distance from postcode center to Schiphol
        from geopy.distance import geodesic
        
        pc_center = (pc_info["center_lat"], pc_info["center_lon"])
        distance_to_schiphol = geodesic(pc_center, self.schiphol_coords).kilometers
        
        # Determine if this area is likely affected by Schiphol traffic
        likely_affected = distance_to_schiphol < 25  # Within 25km of Schiphol
        
        return {
            **pc_info,
            "distance_to_schiphol_km": round(distance_to_schiphol, 1),
            "likely_affected_by_schiphol": likely_affected,
            "schiphol_coords": self.schiphol_coords
        }


if __name__ == "__main__":
    # Test the postal code fetcher
    print("Testing Postal Code Fetcher for Amsterdam Noord 1032...")
    
    areas = AmsterdamAreas()
    
    # Test 1032 postal code
    result = areas.analyze_postcode_vs_schiphol("1032")
    
    print(f"\nPostal Code 1032 Analysis:")
    for key, value in result.items():
        if key != "geometry":  # Skip geometry for cleaner output
            print(f"  {key}: {value}")
    
    # Test boundary checking
    fetcher = PostalCodeFetcher()
    
    # Test coordinates (roughly in Amsterdam Noord area)
    test_lat, test_lon = 52.395, 4.915
    is_in_1032 = fetcher.is_point_in_postcode(test_lat, test_lon, "1032")
    print(f"\nTest point ({test_lat}, {test_lon}) in 1032: {is_in_1032}")