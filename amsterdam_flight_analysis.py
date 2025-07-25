#!/usr/bin/env python3
"""
Main script for analyzing flight patterns over Amsterdam Noord
"""
import json
import sys
from pathlib import Path
import argparse
from datetime import datetime

# Import our custom modules
from opensky_fetcher import OpenSkyFetcher
from flight_analyzer import FlightAnalyzer  
from cache_manager import FlightCache


def load_credentials(cred_path: str = None) -> dict:
    """Load OpenSky API credentials"""
    if cred_path is None:
        # Try common locations
        possible_paths = [
            Path.home() / "Downloads" / "credentials.json",
            Path(".") / "credentials.json",
            Path(".") / "config" / "credentials.json"
        ]
        
        for path in possible_paths:
            if path.exists():
                cred_path = path
                break
    
    if cred_path is None:
        print("No credentials file found. Using anonymous access (limited API calls)")
        return {}
        
    try:
        with open(cred_path, 'r') as f:
            creds = json.load(f)
            
            # Check for OAuth2 credentials (preferred)
            if 'clientId' in creds and 'clientSecret' in creds:
                print(f"Loaded OAuth2 credentials from {cred_path}")
                return {
                    'client_id': creds['clientId'],
                    'client_secret': creds['clientSecret']
                }
            
            # Check for legacy credentials
            elif 'username' in creds and 'password' in creds:
                print(f"Loaded legacy credentials from {cred_path}")
                return {
                    'username': creds['username'],
                    'password': creds['password']
                }
            
            else:
                print("Invalid credentials format - need either clientId/clientSecret or username/password")
                return {}
                
    except Exception as e:
        print(f"Error loading credentials: {e}")
        return {}


def main():
    """Main analysis workflow"""
    parser = argparse.ArgumentParser(description="Amsterdam Noord Flight Pattern Analysis")
    parser.add_argument('--mode', choices=['current', 'historical', 'cached'], 
                       default='current', help='Analysis mode')
    parser.add_argument('--hours', type=int, default=1, 
                       help='Hours of historical data to analyze')
    parser.add_argument('--credentials', type=str, 
                       help='Path to credentials JSON file')
    parser.add_argument('--no-cache', action='store_true', 
                       help='Skip caching of results')
    parser.add_argument('--cleanup', action='store_true',
                       help='Clean up old cache files')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("AMSTERDAM NOORD FLIGHT PATTERN ANALYSIS")
    print("=" * 60)
    print(f"Mode: {args.mode}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Initialize components
    cache = FlightCache()
    analyzer = FlightAnalyzer()
    
    # Handle cleanup if requested
    if args.cleanup:
        print("Cleaning up old cache files...")
        cache.cleanup_old_files()
        print()
    
    # Show cache statistics
    cache_stats = cache.get_cache_stats()
    print("CACHE STATUS:")
    print(f"  OpenSky files: {cache_stats['opensky_files']}")
    print(f"  Total cache size: {cache_stats['total_size_mb']} MB")
    if cache_stats['newest_file']:
        print(f"  Newest file: {cache_stats['newest_file']}")
    print()
    
    # Get flight data based on mode
    flight_data = None
    
    if args.mode == 'cached':
        print("Loading cached data...")
        flight_data = cache.load_opensky_data(hours_back=24)
        
    else:
        # Load credentials
        creds = load_credentials(args.credentials)
        fetcher = OpenSkyFetcher(**creds)
        
        if args.mode == 'current':
            print("Fetching current flight data from OpenSky API...")
            flight_data = fetcher.get_current_flights()
            
        elif args.mode == 'historical':
            print(f"Fetching {args.hours} hours of historical data...")
            flight_data = fetcher.get_historical_flights(args.hours)
        
        # Cache the data unless disabled
        if flight_data is not None and not flight_data.empty and not args.no_cache:
            cache.save_opensky_data(flight_data, args.mode)
    
    # Analyze the data
    if flight_data is None or flight_data.empty:
        print("❌ No flight data available for analysis")
        print("\nPossible reasons:")
        print("  - No flights currently over Amsterdam Noord")
        print("  - API rate limits exceeded")
        print("  - Network connectivity issues")
        print("  - Invalid credentials")
        print("\nTry running with --mode cached to use previously collected data")
        return
    
    print(f"✅ Successfully loaded {len(flight_data)} flight records")
    print()
    
    # Generate text report
    print("GENERATING ANALYSIS REPORT...")
    report = analyzer.generate_report(flight_data)
    print(report)
    
    # Create visualizations
    print("CREATING VISUALIZATIONS...")
    
    try:
        # Create flight map
        print("  📍 Creating flight position map...")
        flight_map = analyzer.create_flight_map(
            flight_data, 
            save_path="amsterdam_flights_map.html"
        )
        
        # Create altitude analysis plots
        print("  📊 Creating altitude distribution plots...")
        analyzer.plot_altitude_distribution(
            flight_data,
            save_path="altitude_analysis.png"
        )
        
        # Create time pattern plots  
        print("  📈 Creating time pattern analysis...")
        analyzer.plot_time_patterns(
            flight_data,
            save_path="time_patterns.png"
        )
        
        print()
        print("✅ Analysis complete!")
        print()
        print("OUTPUT FILES:")
        print("  📄 amsterdam_flights_map.html - Interactive flight map")
        print("  📊 altitude_analysis.png - Altitude distribution charts")
        print("  📈 time_patterns.png - Time-based analysis charts")
        
    except Exception as e:
        print(f"❌ Error creating visualizations: {e}")
        print("This might be due to missing dependencies or display issues")
        print("The text report above still contains valuable insights")
    
    # Additional insights
    if len(flight_data) > 0:
        print()
        print("KEY INSIGHTS:")
        
        # Count low altitude flights
        if 'baro_altitude' in flight_data.columns:
            low_alt = flight_data[flight_data['baro_altitude'] < 3000]
            if len(low_alt) > 0:
                print(f"  ✈️  {len(low_alt)} flights detected below 3000ft (potentially noisy)")
                
        # Most common aircraft types
        if 'aircraft_type' in flight_data.columns:
            most_common = flight_data['aircraft_type'].value_counts().iloc[0]
            print(f"  🏷️  Most common aircraft type: {most_common}")
            
        # International vs domestic
        if 'origin_country' in flight_data.columns:
            dutch_flights = len(flight_data[flight_data['origin_country'] == 'Netherlands'])
            total_flights = len(flight_data)
            intl_percentage = ((total_flights - dutch_flights) / total_flights) * 100
            print(f"  🌍 International flights: {intl_percentage:.1f}%")
    
    print()
    print("💡 TIP: Run with --mode historical --hours 1 to get more comprehensive data")
    print("💡 TIP: Use --mode cached to analyze previously collected data without API calls")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Analysis interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        print("Please check your setup and try again")
        sys.exit(1)