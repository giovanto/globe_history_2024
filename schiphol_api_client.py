"""
Schiphol Airport Official API Client for Flight Schedule and Aircraft Data
Complements OpenSky real-time positioning with official flight information
"""
import requests
import pandas as pd
import time
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import logging
from dataclasses import dataclass


@dataclass
class SchipholFlight:
    """Data structure for Schiphol flight information"""
    flight_id: str
    flight_name: str
    schedule_date: str
    schedule_time: str
    actual_landing_time: Optional[str]
    actual_off_block_time: Optional[str]
    aircraft_type: str
    aircraft_registration: Optional[str]
    flight_direction: str  # 'A' for arrival, 'D' for departure
    airline_iata: str
    airline_icao: str
    destination_iata: Optional[str]
    origin_iata: Optional[str]
    runway: Optional[str]
    gate: Optional[str]
    terminal: Optional[str]
    status: str
    public_estimated_off_block_time: Optional[str]


class SchipholAPIClient:
    """Official Schiphol Airport API client for flight schedules and operations"""
    
    BASE_URL = "https://api.schiphol.nl/public-flights"
    
    def __init__(self, app_id: str, app_key: str):
        """
        Initialize Schiphol API client
        
        Args:
            app_id: Schiphol API application ID
            app_key: Schiphol API application key
        """
        self.app_id = app_id
        self.app_key = app_key
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'app_id': app_id,
            'app_key': app_key,
            'ResourceVersion': 'v4'
        })
        
        # Rate limiting (500 requests per hour for free tier)
        self.request_count = 0
        self.last_reset = datetime.now()
        self.max_requests_per_hour = 500
        
        self.logger = logging.getLogger(__name__)
    
    def _check_rate_limit(self):
        """Check and enforce rate limiting"""
        now = datetime.now()
        if (now - self.last_reset).seconds >= 3600:  # Reset every hour
            self.request_count = 0
            self.last_reset = now
        
        if self.request_count >= self.max_requests_per_hour:
            wait_time = 3600 - (now - self.last_reset).seconds
            self.logger.warning(f"Rate limit reached, waiting {wait_time} seconds")
            time.sleep(wait_time)
            self.request_count = 0
            self.last_reset = datetime.now()
    
    def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """Make authenticated request to Schiphol API"""
        self._check_rate_limit()
        
        try:
            url = f"{self.BASE_URL}/{endpoint}"
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            self.request_count += 1
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Schiphol API request failed: {e}")
            raise
    
    def get_flights_by_schedule_date(self, 
                                   schedule_date: str,
                                   flight_direction: str = 'A',
                                   page: int = 0,
                                   sort: str = '+scheduleTime') -> List[SchipholFlight]:
        """
        Get flights by schedule date
        
        Args:
            schedule_date: Date in YYYY-MM-DD format
            flight_direction: 'A' for arrivals, 'D' for departures
            page: Page number for pagination
            sort: Sort parameter (+scheduleTime, -scheduleTime, etc.)
            
        Returns:
            List of SchipholFlight objects
        """
        params = {
            'scheduleDate': schedule_date,
            'flightDirection': flight_direction,
            'page': page,
            'sort': sort
        }
        
        try:
            data = self._make_request('flights', params)
            flights = []
            
            for flight_data in data.get('flights', []):
                flight = SchipholFlight(
                    flight_id=flight_data.get('id'),
                    flight_name=flight_data.get('flightName'),
                    schedule_date=flight_data.get('scheduleDate'),
                    schedule_time=flight_data.get('scheduleTime'),
                    actual_landing_time=flight_data.get('actualLandingTime'),
                    actual_off_block_time=flight_data.get('actualOffBlockTime'),
                    aircraft_type=flight_data.get('aircraftType', {}).get('iataMain'),
                    aircraft_registration=flight_data.get('aircraftRegistration'),
                    flight_direction=flight_data.get('flightDirection'),
                    airline_iata=flight_data.get('prefixIATA'),
                    airline_icao=flight_data.get('prefixICAO'),
                    destination_iata=flight_data.get('route', {}).get('destinations', [None])[0] if flight_data.get('route') else None,
                    origin_iata=flight_data.get('route', {}).get('destinations', [None])[0] if flight_data.get('route') else None,
                    runway=flight_data.get('runway'),
                    gate=flight_data.get('gate'),
                    terminal=flight_data.get('terminal'),
                    status=flight_data.get('publicFlightState', {}).get('flightStates', [None])[0],
                    public_estimated_off_block_time=flight_data.get('publicEstimatedOffBlockTime')
                )
                flights.append(flight)
            
            return flights
            
        except Exception as e:
            self.logger.error(f"Error fetching flights for {schedule_date}: {e}")
            return []
    
    def get_current_flights(self, hours_window: int = 2) -> Tuple[List[SchipholFlight], List[SchipholFlight]]:
        """
        Get current arrivals and departures within a time window
        
        Args:
            hours_window: Hours before/after current time to fetch
            
        Returns:
            Tuple of (arrivals, departures)
        """
        now = datetime.now()
        schedule_date = now.strftime('%Y-%m-%d')
        
        # Get arrivals and departures for today
        arrivals = self.get_flights_by_schedule_date(schedule_date, 'A')
        departures = self.get_flights_by_schedule_date(schedule_date, 'D')
        
        # Filter by time window
        def is_within_window(flight: SchipholFlight) -> bool:
            try:
                flight_time = datetime.strptime(f"{flight.schedule_date} {flight.schedule_time}", '%Y-%m-%d %H:%M:%S')
                time_diff = abs((flight_time - now).total_seconds() / 3600)
                return time_diff <= hours_window
            except (ValueError, TypeError):
                return False
        
        current_arrivals = [f for f in arrivals if is_within_window(f)]
        current_departures = [f for f in departures if is_within_window(f)]
        
        return current_arrivals, current_departures
    
    def get_runway_usage_patterns(self, schedule_date: str) -> Dict[str, int]:
        """
        Analyze runway usage patterns for a specific date
        
        Args:
            schedule_date: Date in YYYY-MM-DD format
            
        Returns:
            Dictionary mapping runway names to usage counts
        """
        arrivals = self.get_flights_by_schedule_date(schedule_date, 'A')
        departures = self.get_flights_by_schedule_date(schedule_date, 'D')
        
        runway_usage = {}
        
        for flight in arrivals + departures:
            if flight.runway:
                runway_usage[flight.runway] = runway_usage.get(flight.runway, 0) + 1
        
        return runway_usage
    
    def flights_to_dataframe(self, flights: List[SchipholFlight]) -> pd.DataFrame:
        """Convert list of SchipholFlight objects to pandas DataFrame"""
        if not flights:
            return pd.DataFrame()
        
        data = []
        for flight in flights:
            data.append({
                'flight_id': flight.flight_id,
                'flight_name': flight.flight_name,
                'schedule_date': flight.schedule_date,
                'schedule_time': flight.schedule_time,
                'actual_landing_time': flight.actual_landing_time,
                'actual_off_block_time': flight.actual_off_block_time,
                'aircraft_type': flight.aircraft_type,
                'aircraft_registration': flight.aircraft_registration,
                'flight_direction': flight.flight_direction,
                'airline_iata': flight.airline_iata,
                'airline_icao': flight.airline_icao,
                'destination_iata': flight.destination_iata,
                'origin_iata': flight.origin_iata,
                'runway': flight.runway,
                'gate': flight.gate,
                'terminal': flight.terminal,
                'status': flight.status,
                'public_estimated_off_block_time': flight.public_estimated_off_block_time
            })
        
        return pd.DataFrame(data)


class AircraftDatabase:
    """Enhanced aircraft database for noise level estimation"""
    
    def __init__(self):
        self.noise_levels = {
            # Wide-body aircraft (loudest)
            'A380': {'noise_db': 85, 'category': 'Super Heavy', 'engines': 4},
            'B747': {'noise_db': 84, 'category': 'Heavy', 'engines': 4},
            'B777': {'noise_db': 82, 'category': 'Heavy', 'engines': 2},
            'A350': {'noise_db': 78, 'category': 'Heavy', 'engines': 2},
            'B787': {'noise_db': 77, 'category': 'Heavy', 'engines': 2},
            'A340': {'noise_db': 83, 'category': 'Heavy', 'engines': 4},
            'B767': {'noise_db': 81, 'category': 'Heavy', 'engines': 2},
            'A330': {'noise_db': 80, 'category': 'Heavy', 'engines': 2},
            
            # Narrow-body aircraft
            'B737': {'noise_db': 75, 'category': 'Medium', 'engines': 2},
            'A320': {'noise_db': 74, 'category': 'Medium', 'engines': 2},
            'A321': {'noise_db': 76, 'category': 'Medium', 'engines': 2},
            'A319': {'noise_db': 73, 'category': 'Medium', 'engines': 2},
            'B757': {'noise_db': 79, 'category': 'Medium', 'engines': 2},
            
            # Regional aircraft (quieter)
            'E190': {'noise_db': 72, 'category': 'Regional', 'engines': 2},
            'E175': {'noise_db': 71, 'category': 'Regional', 'engines': 2},
            'CRJ': {'noise_db': 70, 'category': 'Regional', 'engines': 2},
            'ATR': {'noise_db': 68, 'category': 'Regional', 'engines': 2},
            'DH8': {'noise_db': 69, 'category': 'Regional', 'engines': 2},
        }
    
    def get_aircraft_info(self, aircraft_type: str) -> Dict[str, Any]:
        """Get aircraft noise and category information"""
        if not aircraft_type:
            return {'noise_db': 75, 'category': 'Unknown', 'engines': 2}  # Default
        
        # Try exact match first
        if aircraft_type in self.noise_levels:
            return self.noise_levels[aircraft_type]
        
        # Try partial matches
        for key, value in self.noise_levels.items():
            if key in aircraft_type or aircraft_type in key:
                return value
        
        # Default for unknown aircraft
        return {'noise_db': 75, 'category': 'Unknown', 'engines': 2}


if __name__ == "__main__":
    # Test the Schiphol API client
    # Note: You need to register at https://developer.schiphol.nl/ to get API credentials
    
    print("Schiphol API Client - Test Mode")
    print("Note: This requires valid Schiphol API credentials")
    print("Register at https://developer.schiphol.nl/ to obtain app_id and app_key")
    
    # Uncomment and add your credentials to test:
    # client = SchipholAPIClient("your_app_id", "your_app_key")
    # arrivals, departures = client.get_current_flights()
    # print(f"Current arrivals: {len(arrivals)}")
    # print(f"Current departures: {len(departures)}")
EOF < /dev/null