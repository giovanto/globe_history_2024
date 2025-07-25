#!/usr/bin/env python3
"""
Debug script to validate our Schiphol flight analysis methodology
"""
import json
import time
from datetime import datetime, timedelta
import pandas as pd
from opensky_fetcher import OpenSkyFetcher


def load_credentials():
    """Load OpenSky API credentials"""
    try:
        with open("credentials.json", 'r') as f:
            creds = json.load(f)
            return {
                'client_id': creds['clientId'],
                'client_secret': creds['clientSecret']
            }
    except Exception as e:
        print(f"Error loading credentials: {e}")
        return {}


def test_api_endpoints():
    """Test different OpenSky API endpoints and parameters"""
    print("=" * 60)
    print("DEBUGGING OPENSKY API METHODOLOGY")  
    print("=" * 60)
    
    creds = load_credentials()
    fetcher = OpenSkyFetcher(**creds)
    
    # Test 1: Current flights globally (no bounds)
    print("\n🧪 TEST 1: Global current flights (no geographic bounds)")
    print("-" * 50)
    
    # Temporarily remove bounds to get global data
    original_bounds = fetcher.AMSTERDAM_NOORD_BOUNDS.copy()
    fetcher.AMSTERDAM_NOORD_BOUNDS = {}  # No bounds = global
    
    try:
        global_flights = fetcher.get_current_flights()
        print(f"✅ Global flights detected: {len(global_flights)}")
        if not global_flights.empty:
            print(f"   Sample countries: {global_flights['origin_country'].value_counts().head(3).to_dict()}")
    except Exception as e:
        print(f"❌ Global flights failed: {e}")
    finally:
        fetcher.AMSTERDAM_NOORD_BOUNDS = original_bounds
    
    # Test 2: Current flights with Schiphol-focused bounds
    print("\n🧪 TEST 2: Schiphol area current flights")
    print("-" * 50)
    
    # Set bounds around Schiphol (tighter than our original)
    schiphol_bounds = {
        'lat_min': 52.0,   # Roughly 35km south of Schiphol  
        'lat_max': 52.6,   # Roughly 35km north of Schiphol
        'lon_min': 4.3,    # Roughly 30km west of Schiphol
        'lon_max': 5.0     # Roughly 30km east of Schiphol
    }
    
    fetcher.AMSTERDAM_NOORD_BOUNDS = schiphol_bounds
    
    try:
        schiphol_flights = fetcher.get_current_flights()
        print(f"✅ Schiphol area flights: {len(schiphol_flights)}")
        if not schiphol_flights.empty:
            print(f"   Altitude range: {schiphol_flights['baro_altitude'].min():.0f} - {schiphol_flights['baro_altitude'].max():.0f} ft")
            print(f"   Countries: {schiphol_flights['origin_country'].value_counts().head(3).to_dict()}")
    except Exception as e:
        print(f"❌ Schiphol area flights failed: {e}")
    
    # Test 3: Different time windows for historical data
    print("\n🧪 TEST 3: Historical data time windows")
    print("-" * 50)
    
    # Test small time windows
    for minutes_back in [5, 15, 30, 60]:
        try:
            # Manual API call for specific time
            current_time = int(time.time())
            past_time = current_time - (minutes_back * 60)
            
            url = f"{fetcher.BASE_URL}/states/all"
            params = {
                'time': past_time,
                'lamin': schiphol_bounds['lat_min'],
                'lamax': schiphol_bounds['lat_max'], 
                'lomin': schiphol_bounds['lon_min'],
                'lomax': schiphol_bounds['lon_max']
            }
            
            headers = fetcher._get_auth_headers()
            response = fetcher.session.get(url, params=params, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                flight_count = len(data.get('states', [])) if data.get('states') else 0
                print(f"   {minutes_back} minutes ago: {flight_count} flights")
            else:
                print(f"   {minutes_back} minutes ago: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"   {minutes_back} minutes ago: Error - {e}")
    
    # Test 4: Manual API call without geographic bounds
    print("\n🧪 TEST 4: Raw API without bounds (should show many flights)")
    print("-" * 50)
    
    try:
        url = f"{fetcher.BASE_URL}/states/all" 
        headers = fetcher._get_auth_headers()
        response = fetcher.session.get(url, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            total_flights = len(data.get('states', [])) if data.get('states') else 0
            print(f"✅ Total global flights right now: {total_flights}")
            
            if data.get('states'):
                # Count flights near Schiphol manually
                schiphol_lat, schiphol_lon = 52.3105, 4.7683
                nearby_count = 0
                
                for state in data['states']:
                    if state[6] is not None and state[5] is not None:  # lat, lon not null
                        lat, lon = state[6], state[5]
                        # Simple distance check (rough)
                        if abs(lat - schiphol_lat) < 0.5 and abs(lon - schiphol_lon) < 0.5:
                            nearby_count += 1
                
                print(f"   Flights within ~50km of Schiphol: {nearby_count}")
        else:
            print(f"❌ Raw API failed: HTTP {response.status_code}")
            if response.status_code == 403:
                print("   This suggests authentication/rate limiting issues")
    
    except Exception as e:
        print(f"❌ Raw API failed: {e}")
    
    # Test 5: Check account limitations
    print("\n🧪 TEST 5: Account limitations check")
    print("-" * 50)
    
    try:
        # Check what our token allows
        headers = fetcher._get_auth_headers()
        print(f"   Auth method: {fetcher.auth_method}")
        print(f"   Has valid token: {bool(fetcher.access_token)}")
        
        # Try different endpoints
        test_endpoints = [
            "/states/all",
            "/flights/all", 
            "/flights/departure"
        ]
        
        for endpoint in test_endpoints:
            try:
                response = fetcher.session.get(
                    f"{fetcher.BASE_URL}{endpoint}",
                    headers=headers,
                    params={'lamin': 52.2, 'lamax': 52.4, 'lomin': 4.6, 'lomax': 4.9},
                    timeout=10
                )
                print(f"   {endpoint}: HTTP {response.status_code}")
            except Exception as e:
                print(f"   {endpoint}: Error - {str(e)[:50]}")
    
    except Exception as e:
        print(f"❌ Account check failed: {e}")
    
    # Test 6: Time calculation validation
    print("\n🧪 TEST 6: Time calculation validation")
    print("-" * 50)
    
    current_time = int(time.time())
    hours_back = 24
    calculated_past = current_time - (hours_back * 3600)
    
    print(f"   Current timestamp: {current_time} ({datetime.fromtimestamp(current_time)})")
    print(f"   24 hours ago timestamp: {calculated_past} ({datetime.fromtimestamp(calculated_past)})")
    print(f"   Difference: {(current_time - calculated_past) / 3600:.1f} hours")
    
    # Restore original bounds
    fetcher.AMSTERDAM_NOORD_BOUNDS = original_bounds
    
    print("\n" + "=" * 60)
    print("DEBUGGING COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_api_endpoints()