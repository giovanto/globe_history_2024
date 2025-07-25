#!/usr/bin/env python3
"""
OpenSky 2025 Flight Data Collector
Automated 24/7 data collection system optimized for OpenSky API limits
"""
import json
import time
import schedule
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import logging
from typing import Dict, List
import os
import signal
import sys

# Import our modules
from opensky_fetcher import OpenSkyFetcher
from schiphol_analyzer import SchipholFlightAnalyzer


class OpenSky2025Collector:
    """24/7 automated flight data collector optimized for OpenSky API"""
    
    def __init__(self, db_path: str = "flight_data_2025.db"):
        """Initialize the collector"""
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('flight_collector.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Database setup
        self.db_path = db_path
        self.setup_database()
        
        # Collection settings optimized for OpenSky limits
        self.collection_settings = {
            # Collect every 5 minutes = 288 collections/day
            # 288 * 2 API calls (local + schiphol) = 576 API calls/day
            # Well under 4000 credit limit
            'interval_minutes': 5,
            
            # Geographic areas
            'local_bounds': {  # Amsterdam Noord 1032 area
                'lat_min': 52.35, 'lat_max': 52.45,
                'lon_min': 4.85, 'lon_max': 4.95
            },
            'schiphol_bounds': {  # Schiphol area 
                'lat_min': 52.0, 'lat_max': 52.6,
                'lon_min': 4.3, 'lon_max': 5.0
            }
        }
        
        # Initialize components
        self.fetcher = None
        self.analyzer = SchipholFlightAnalyzer()
        self.running = False
        
        # Statistics tracking
        self.stats = {
            'collections_today': 0,
            'api_calls_today': 0,
            'flights_collected_today': 0,
            'last_reset': datetime.now().date()
        }
        
        # Graceful shutdown handling
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def setup_database(self):
        """Setup SQLite database for efficient flight data storage"""
        conn = sqlite3.connect(self.db_path)
        
        # Main flights table - optimized for time-series data
        conn.execute('''
            CREATE TABLE IF NOT EXISTS flights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_time TIMESTAMP NOT NULL,
                icao24 TEXT NOT NULL,
                callsign TEXT,
                origin_country TEXT,
                time_position REAL,
                last_contact REAL,
                longitude REAL,
                latitude REAL,
                baro_altitude REAL,
                on_ground BOOLEAN,
                velocity REAL,
                true_track REAL,
                vertical_rate REAL,
                geo_altitude REAL,
                squawk TEXT,
                spi BOOLEAN,
                position_source INTEGER,
                area_type TEXT NOT NULL,  -- 'local' or 'schiphol'
                
                -- Analysis fields (computed during collection)
                distance_to_house_km REAL,
                estimated_noise_db REAL,
                schiphol_operation TEXT,
                approach_corridor TEXT,
                aircraft_category TEXT
            )
        ''')
        
        # Indexes for efficient querying
        conn.execute('CREATE INDEX IF NOT EXISTS idx_collection_time ON flights(collection_time)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_icao24_time ON flights(icao24, collection_time)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_area_time ON flights(area_type, collection_time)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_coordinates ON flights(latitude, longitude)')
        
        # Daily statistics table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                date DATE PRIMARY KEY,
                total_collections INTEGER,
                total_api_calls INTEGER,
                total_flights INTEGER,
                local_flights INTEGER,
                schiphol_flights INTEGER,
                unique_aircraft INTEGER,
                high_noise_flights INTEGER,
                errors INTEGER
            )
        ''')
        
        # Collection log table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS collection_log (
                timestamp TIMESTAMP PRIMARY KEY,
                area_type TEXT,
                flights_collected INTEGER,
                api_success BOOLEAN,
                error_message TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
        self.logger.info(f"Database initialized: {self.db_path}")
    
    def load_credentials(self) -> Dict:
        """Load OpenSky credentials"""
        try:
            with open("credentials.json", 'r') as f:
                creds = json.load(f)
                return {
                    'client_id': creds['clientId'],
                    'client_secret': creds['clientSecret']
                }
        except Exception as e:
            self.logger.error(f"Error loading credentials: {e}")
            return {}
    
    def collect_flight_data(self, area_type: str) -> pd.DataFrame:
        """Collect flight data for specified area"""
        if not self.fetcher:
            creds = self.load_credentials()
            self.fetcher = OpenSkyFetcher(**creds)
        
        # Set appropriate bounds
        if area_type == 'local':
            self.fetcher.AMSTERDAM_NOORD_BOUNDS = self.collection_settings['local_bounds']
        else:  # schiphol
            self.fetcher.AMSTERDAM_NOORD_BOUNDS = self.collection_settings['schiphol_bounds']
        
        try:
            flights = self.fetcher.get_current_flights()
            self.stats['api_calls_today'] += 1
            
            if not flights.empty:
                # Add collection metadata
                flights['collection_time'] = datetime.now()
                flights['area_type'] = area_type
                
                # Enhance with analysis data
                flights = self.enhance_flight_data(flights, area_type)
                
                self.logger.info(f"Collected {len(flights)} flights for {area_type} area")
                
                # Log success
                self.log_collection(area_type, len(flights), True, None)
                
                return flights
            else:
                self.logger.info(f"No flights found in {area_type} area")
                self.log_collection(area_type, 0, True, None)
                return pd.DataFrame()
                
        except Exception as e:
            self.logger.error(f"Error collecting {area_type} data: {e}")
            self.log_collection(area_type, 0, False, str(e))
            return pd.DataFrame()
    
    def enhance_flight_data(self, flights: pd.DataFrame, area_type: str) -> pd.DataFrame:
        """Enhance flight data with analysis during collection"""
        if flights.empty:
            return flights
        
        # Amsterdam Noord coordinates (your house)
        house_coords = (52.395, 4.915)
        
        # Calculate distance to house
        def calc_distance(row):
            if pd.isna(row['latitude']) or pd.isna(row['longitude']):
                return float('inf')
            from geopy.distance import geodesic
            return geodesic((row['latitude'], row['longitude']), house_coords).kilometers
        
        flights['distance_to_house_km'] = flights.apply(calc_distance, axis=1)
        
        # Estimate noise impact
        flights = self.analyzer.calculate_noise_impact(flights, house_coords)
        
        # Identify Schiphol operations
        flights = self.analyzer.identify_schiphol_operations(flights)
        
        # Enhanced aircraft classification
        if 'icao24' in flights.columns:
            classifications = flights.apply(
                lambda row: self.analyzer.classify_aircraft_by_icao(
                    row.get('icao24', ''), 
                    row.get('callsign', '')
                ), axis=1
            )
            flights['aircraft_category'] = [c.get('category', 'Unknown') for c in classifications]
        
        return flights
    
    def store_flight_data(self, flights: pd.DataFrame):
        """Store flight data in database"""
        if flights.empty:
            return
        
        conn = sqlite3.connect(self.db_path)
        
        try:
            # Select columns that match database schema
            db_columns = [
                'collection_time', 'icao24', 'callsign', 'origin_country',
                'time_position', 'last_contact', 'longitude', 'latitude',
                'baro_altitude', 'on_ground', 'velocity', 'true_track',
                'vertical_rate', 'geo_altitude', 'squawk', 'spi',
                'position_source', 'area_type', 'distance_to_house_km',
                'estimated_noise_db', 'schiphol_operation', 'approach_corridor',
                'aircraft_category'
            ]
            
            # Ensure all columns exist in flights DataFrame
            for col in db_columns:
                if col not in flights.columns:
                    if col in ['estimated_noise_db', 'distance_to_house_km']:
                        flights[col] = 0.0
                    else:
                        flights[col] = None
            
            # Store to database
            flights[db_columns].to_sql('flights', conn, if_exists='append', index=False)
            
            self.stats['flights_collected_today'] += len(flights)
            self.logger.info(f"Stored {len(flights)} flights to database")
            
        except Exception as e:
            self.logger.error(f"Error storing flight data: {e}")
        finally:
            conn.close()
    
    def log_collection(self, area_type: str, flights_count: int, success: bool, error_msg: str):
        """Log collection attempt"""
        conn = sqlite3.connect(self.db_path)
        
        conn.execute('''
            INSERT INTO collection_log (timestamp, area_type, flights_collected, api_success, error_message)
            VALUES (?, ?, ?, ?, ?)
        ''', (datetime.now(), area_type, flights_count, success, error_msg))
        
        conn.commit()
        conn.close()
    
    def update_daily_stats(self):
        """Update daily statistics"""
        today = datetime.now().date()
        
        conn = sqlite3.connect(self.db_path)
        
        # Get today's statistics
        today_stats = conn.execute('''
            SELECT 
                COUNT(*) as total_flights,
                COUNT(CASE WHEN area_type = 'local' THEN 1 END) as local_flights,
                COUNT(CASE WHEN area_type = 'schiphol' THEN 1 END) as schiphol_flights,
                COUNT(DISTINCT icao24) as unique_aircraft,
                COUNT(CASE WHEN estimated_noise_db >= 65 THEN 1 END) as high_noise_flights
            FROM flights 
            WHERE DATE(collection_time) = ?
        ''', (today,)).fetchone()
        
        collections_today = conn.execute('''
            SELECT COUNT(*) FROM collection_log 
            WHERE DATE(timestamp) = ? AND api_success = 1
        ''', (today,)).fetchone()[0]
        
        errors_today = conn.execute('''
            SELECT COUNT(*) FROM collection_log 
            WHERE DATE(timestamp) = ? AND api_success = 0
        ''', (today,)).fetchone()[0]
        
        # Insert or update daily stats
        conn.execute('''
            INSERT OR REPLACE INTO daily_stats 
            (date, total_collections, total_api_calls, total_flights, local_flights, 
             schiphol_flights, unique_aircraft, high_noise_flights, errors)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (today, collections_today, self.stats['api_calls_today'], 
              today_stats[0], today_stats[1], today_stats[2], 
              today_stats[3], today_stats[4], errors_today))
        
        conn.commit()
        conn.close()
    
    def run_collection_cycle(self):
        """Run one complete collection cycle"""
        self.logger.info("Starting collection cycle")
        
        # Reset daily stats if new day
        today = datetime.now().date()
        if today != self.stats['last_reset']:
            self.stats = {
                'collections_today': 0,
                'api_calls_today': 0,
                'flights_collected_today': 0,
                'last_reset': today
            }
            self.logger.info("Reset daily statistics for new day")
        
        # Collect local area data
        local_flights = self.collect_flight_data('local')
        if not local_flights.empty:
            self.store_flight_data(local_flights)
        
        # Small delay between API calls
        time.sleep(2)
        
        # Collect Schiphol area data
        schiphol_flights = self.collect_flight_data('schiphol')
        if not schiphol_flights.empty:
            self.store_flight_data(schiphol_flights)
        
        # Update statistics
        self.stats['collections_today'] += 1
        self.update_daily_stats()
        
        # Log progress
        self.logger.info(f"Collection cycle complete. Today: {self.stats['collections_today']} cycles, "
                        f"{self.stats['api_calls_today']} API calls, "
                        f"{self.stats['flights_collected_today']} flights")
    
    def start_automated_collection(self):
        """Start automated 24/7 collection"""
        self.logger.info("Starting automated flight data collection")
        self.logger.info(f"Collection interval: {self.collection_settings['interval_minutes']} minutes")
        
        # Schedule collection every N minutes
        schedule.every(self.collection_settings['interval_minutes']).minutes.do(self.run_collection_cycle)
        
        # Run initial collection
        self.run_collection_cycle()
        
        self.running = True
        
        # Main collection loop
        while self.running:
            schedule.run_pending()
            time.sleep(10)  # Check every 10 seconds
        
        self.logger.info("Automated collection stopped")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
    
    def get_collection_status(self) -> Dict:
        """Get current collection status"""
        conn = sqlite3.connect(self.db_path)
        
        # Get overall statistics
        total_flights = conn.execute('SELECT COUNT(*) FROM flights').fetchone()[0]
        total_days = conn.execute('SELECT COUNT(DISTINCT DATE(collection_time)) FROM flights').fetchone()[0]
        
        # Get today's statistics
        today = datetime.now().date()
        today_stats = conn.execute('''
            SELECT 
                COUNT(*) as flights,
                COUNT(DISTINCT icao24) as aircraft,
                MIN(collection_time) as first_collection,
                MAX(collection_time) as last_collection
            FROM flights 
            WHERE DATE(collection_time) = ?
        ''', (today,)).fetchone()
        
        conn.close()
        
        return {
            'total_flights_collected': total_flights,
            'collection_days': total_days,
            'today_flights': today_stats[0],
            'today_aircraft': today_stats[1],
            'first_collection_today': today_stats[2],
            'last_collection_today': today_stats[3],
            'api_calls_today': self.stats['api_calls_today'],
            'collections_today': self.stats['collections_today']
        }


def main():
    """Main function to run the collector"""
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenSky 2025 Flight Data Collector")
    parser.add_argument('--start', action='store_true', help='Start automated collection')
    parser.add_argument('--status', action='store_true', help='Show collection status')
    parser.add_argument('--test', action='store_true', help='Run single collection test')
    parser.add_argument('--db', default='flight_data_2025.db', help='Database path')
    
    args = parser.parse_args()
    
    collector = OpenSky2025Collector(args.db)
    
    if args.status:
        status = collector.get_collection_status()
        print("\n" + "="*60)
        print("OPENSKY 2025 COLLECTION STATUS")
        print("="*60)
        for key, value in status.items():
            print(f"{key}: {value}")
        print("="*60)
    
    elif args.test:
        print("Running single collection test...")
        collector.run_collection_cycle()
        print("Test complete!")
    
    elif args.start:
        print("Starting automated 24/7 collection...")
        print("Press Ctrl+C to stop gracefully")
        collector.start_automated_collection()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()