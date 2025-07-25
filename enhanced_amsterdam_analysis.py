#!/usr/bin/env python3
"""
Enhanced Amsterdam Noord 1032 Flight Analysis with Schiphol Traffic Integration
Combines local residential impact analysis with broader Schiphol operations insight
"""
import json
import sys
from pathlib import Path
import argparse
from datetime import datetime
import pandas as pd

# Import our enhanced modules
from opensky_fetcher import OpenSkyFetcher
from postal_code_fetcher import PostalCodeFetcher, AmsterdamAreas
from schiphol_analyzer import SchipholFlightAnalyzer
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


class EnhancedAmsterdamAnalysis:
    """Enhanced analysis combining local 1032 area with broader Schiphol operations"""
    
    def __init__(self, postcode: str = "1032"):
        """Initialize enhanced analyzer"""
        self.postcode = postcode
        
        # Initialize components
        self.cache = FlightCache()
        self.pc_fetcher = PostalCodeFetcher()
        self.areas = AmsterdamAreas()  
        self.schiphol_analyzer = SchipholFlightAnalyzer()
        self.flight_analyzer = FlightAnalyzer()
        
        # Get precise postal code info
        self.pc_info = self.areas.analyze_postcode_vs_schiphol(postcode)
        
        if "error" not in self.pc_info:
            self.target_coords = (self.pc_info["center_lat"], self.pc_info["center_lon"])
            print(f"📍 Targeting postal code {postcode}: {self.pc_info['center_lat']:.4f}, {self.pc_info['center_lon']:.4f}")
            print(f"   Distance to Schiphol: {self.pc_info['distance_to_schiphol_km']} km")
            print(f"   Area: {self.pc_info['area_km2']} km²")
        else:
            print(f"⚠️  Could not get precise coordinates for {postcode}, using approximate center")
            self.target_coords = (52.395, 4.915)  # Approximate Amsterdam Noord center
    
    def get_dual_flight_data(self, fetcher: OpenSkyFetcher, mode: str = "current") -> tuple:
        """
        Get both local 1032 area flights and broader Schiphol approach area flights
        
        Returns:
            Tuple of (local_flights_df, schiphol_area_flights_df)
        """
        print("🔍 Fetching flight data for dual analysis...")
        
        # 1. Get local area flights (existing functionality)
        if mode == "current":
            local_flights = fetcher.get_current_flights()
        else:
            local_flights = fetcher.get_historical_flights(1)
        
        # 2. Get broader Schiphol approach area flights
        print("🛫 Fetching Schiphol approach area flights...")
        
        # Temporarily expand search area for Schiphol operations
        original_bounds = fetcher.AMSTERDAM_NOORD_BOUNDS.copy()
        
        # Expand to cover Schiphol approach corridors
        schiphol_approach_bounds = {
            'lat_min': 52.0,   # South of Schiphol
            'lat_max': 52.7,   # North of Amsterdam 
            'lon_min': 4.5,    # West of Amsterdam
            'lon_max': 5.2     # East of Amsterdam
        }
        
        fetcher.AMSTERDAM_NOORD_BOUNDS = schiphol_approach_bounds
        
        try:
            if mode == "current":
                schiphol_flights = fetcher.get_current_flights()
            else:
                schiphol_flights = fetcher.get_historical_flights(1)
        finally:
            # Restore original bounds
            fetcher.AMSTERDAM_NOORD_BOUNDS = original_bounds
        
        print(f"📊 Local area flights: {len(local_flights) if not local_flights.empty else 0}")
        print(f"📊 Schiphol area flights: {len(schiphol_flights) if not schiphol_flights.empty else 0}")
        
        return local_flights, schiphol_flights
    
    def analyze_comprehensive(self, local_flights: pd.DataFrame, 
                            schiphol_flights: pd.DataFrame) -> dict:
        """
        Perform comprehensive analysis combining local and Schiphol perspectives
        """
        analysis_results = {
            "timestamp": datetime.now().isoformat(),
            "postcode": self.postcode,
            "target_coordinates": self.target_coords
        }
        
        # 1. Local area analysis (focused on residential impact)
        print("🏠 Analyzing local residential impact...")
        if not local_flights.empty:
            local_analysis = self.schiphol_analyzer.analyze_residential_impact(
                local_flights, self.target_coords, self.postcode
            )
            analysis_results["local_area_analysis"] = local_analysis
        else:
            analysis_results["local_area_analysis"] = {"error": "No local flights detected"}
        
        # 2. Schiphol operations analysis (broader traffic patterns)
        print("✈️  Analyzing Schiphol traffic patterns...")
        if not schiphol_flights.empty:
            # Process Schiphol flights
            processed_schiphol = self.schiphol_analyzer.identify_schiphol_operations(schiphol_flights)
            
            # Filter for actual Schiphol operations
            schiphol_ops = processed_schiphol[
                processed_schiphol['schiphol_operation'].isin([
                    'Landing/Takeoff', 'Approach/Departure', 'Extended Approach'
                ])
            ]
            
            schiphol_analysis = {
                "total_area_flights": len(schiphol_flights),
                "schiphol_operations": len(schiphol_ops),
                "operation_breakdown": processed_schiphol['schiphol_operation'].value_counts().to_dict(),
                "approach_corridors": processed_schiphol['approach_corridor'].value_counts().to_dict(),
                "average_altitude": round(schiphol_flights['baro_altitude'].mean(), 0) if 'baro_altitude' in schiphol_flights.columns else None,
                "flights_over_noord": len(schiphol_flights[
                    (schiphol_flights['latitude'] >= 52.37) & 
                    (schiphol_flights['latitude'] <= 52.43) &
                    (schiphol_flights['longitude'] >= 4.85) &
                    (schiphol_flights['longitude'] <= 4.95)
                ])
            }
            
            analysis_results["schiphol_operations_analysis"] = schiphol_analysis
        else:
            analysis_results["schiphol_operations_analysis"] = {"error": "No Schiphol area flights detected"}
        
        # 3. Comparative analysis
        print("📈 Performing comparative analysis...")
        if not local_flights.empty and not schiphol_flights.empty:
            comparative = {
                "local_vs_total_percentage": round((len(local_flights) / len(schiphol_flights)) * 100, 1),
                "high_impact_local_flights": len(local_flights[local_flights.get('estimated_noise_db', 0) >= 65]) if 'estimated_noise_db' in local_flights.columns else 0,
                "schiphol_traffic_overhead": len(schiphol_flights[
                    (schiphol_flights['latitude'] >= self.target_coords[0] - 0.01) &
                    (schiphol_flights['latitude'] <= self.target_coords[0] + 0.01) &
                    (schiphol_flights['longitude'] >= self.target_coords[1] - 0.01) &
                    (schiphol_flights['longitude'] <= self.target_coords[1] + 0.01)
                ])
            }
            
            analysis_results["comparative_analysis"] = comparative
        
        return analysis_results
    
    def generate_enhanced_report(self, analysis: dict) -> str:
        """Generate comprehensive text report"""
        report = f"""
═══════════════════════════════════════════════════════════════
    ENHANCED AMSTERDAM NOORD {self.postcode} FLIGHT ANALYSIS    
═══════════════════════════════════════════════════════════════
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Target: Postal Code {self.postcode} ({self.target_coords[0]:.4f}, {self.target_coords[1]:.4f})

🏠 LOCAL RESIDENTIAL IMPACT ANALYSIS
──────────────────────────────────────────────────────────────
"""
        
        local_analysis = analysis.get("local_area_analysis", {})
        if "error" not in local_analysis:
            report += f"""
Total flights detected over {self.postcode}: {local_analysis.get('total_flights', 0)}

NOISE IMPACT:
"""
            noise_analysis = local_analysis.get("noise_analysis", {})
            if noise_analysis:
                for impact, count in noise_analysis.get("impact_distribution", {}).items():
                    report += f"  • {impact}: {count} flights\n"
                
                report += f"""
  • Average noise level: {noise_analysis.get('average_noise_level', 'N/A')} dB
  • High impact flights (≥65dB): {noise_analysis.get('high_impact_flights', 0)}
  • Loudest aircraft: {', '.join(noise_analysis.get('high_noise_aircraft', [])[:3])}

"""
            
            # Schiphol operations for local area
            schiphol_ops = local_analysis.get("schiphol_operations", {})
            if schiphol_ops:
                report += f"""SCHIPHOL OPERATIONS AFFECTING YOUR AREA:
  • Direct overhead (within 2km): {schiphol_ops.get('direct_overhead', 0)} flights
  • Likely Schiphol traffic: {schiphol_ops.get('likely_schiphol_traffic', 0)} flights
  
  Operation types:
"""
                for op_type, count in schiphol_ops.get("operation_types", {}).items():
                    report += f"    - {op_type}: {count}\n"
                
                report += "\n  Approach corridors:\n"
                for corridor, count in schiphol_ops.get("approach_corridors", {}).items():
                    report += f"    - {corridor}: {count}\n"
        else:
            report += "  No flights detected in local area\n"
        
        report += f"""

✈️  BROADER SCHIPHOL TRAFFIC ANALYSIS
──────────────────────────────────────────────────────────────
"""
        
        schiphol_analysis = analysis.get("schiphol_operations_analysis", {})
        if "error" not in schiphol_analysis:
            report += f"""
Total flights in Schiphol area: {schiphol_analysis.get('total_area_flights', 0)}
Confirmed Schiphol operations: {schiphol_analysis.get('schiphol_operations', 0)}
Flights over Amsterdam Noord region: {schiphol_analysis.get('flights_over_noord', 0)}
Average flight altitude: {schiphol_analysis.get('average_altitude', 'N/A')} feet

OPERATION BREAKDOWN:
"""
            for operation, count in schiphol_analysis.get("operation_breakdown", {}).items():
                percentage = (count / schiphol_analysis.get('total_area_flights', 1)) * 100
                report += f"  • {operation}: {count} ({percentage:.1f}%)\n"
            
            report += "\nAPPROACH CORRIDORS:\n"
            for corridor, count in schiphol_analysis.get("approach_corridors", {}).items():
                report += f"  • {corridor}: {count} flights\n"
        else:
            report += "  No Schiphol area flights detected\n"
        
        # Comparative analysis
        comparative = analysis.get("comparative_analysis", {})
        if comparative:
            report += f"""

📊 COMPARATIVE INSIGHTS
──────────────────────────────────────────────────────────────
• Your area represents {comparative.get('local_vs_total_percentage', 0)}% of detected Schiphol area traffic
• High-impact flights directly over {self.postcode}: {comparative.get('high_impact_local_flights', 0)}
• Schiphol traffic passing directly overhead: {comparative.get('schiphol_traffic_overhead', 0)}
"""
        
        report += f"""

💡 KEY TAKEAWAYS
──────────────────────────────────────────────────────────────
"""
        
        # Generate insights based on data
        if local_analysis and "error" not in local_analysis:
            noise_data = local_analysis.get("noise_analysis", {})
            high_impact = noise_data.get("high_impact_flights", 0)
            
            if high_impact > 0:
                report += f"⚠️  {high_impact} flights caused high noise impact (≥65dB) over your area\n"
            
            total_local = local_analysis.get("total_flights", 0)
            if total_local > 0:
                report += f"📍 {total_local} flights detected directly over postal code {self.postcode}\n"
        
        if schiphol_analysis and "error" not in schiphol_analysis:
            noord_flights = schiphol_analysis.get("flights_over_noord", 0)
            if noord_flights > 0:
                report += f"🛫 {noord_flights} Schiphol-related flights passed over Amsterdam Noord region\n"
        
        report += f"""
🔄 This analysis combines hyperlocal monitoring of your {self.postcode} area with 
   broader Schiphol traffic patterns to give you complete situational awareness.

💡 For historical trends, run: --mode historical --hours 1
💡 For cached analysis, run: --mode cached
"""
        
        return report


def main():
    """Enhanced main analysis workflow"""
    parser = argparse.ArgumentParser(description="Enhanced Amsterdam Noord Flight Analysis")
    parser.add_argument('--mode', choices=['current', 'historical', 'cached'], 
                       default='current', help='Analysis mode')
    parser.add_argument('--hours', type=int, default=1, 
                       help='Hours of historical data to analyze')
    parser.add_argument('--postcode', type=str, default='1032',
                       help='Amsterdam postal code to analyze')
    parser.add_argument('--credentials', type=str, 
                       help='Path to credentials JSON file')
    parser.add_argument('--no-cache', action='store_true', 
                       help='Skip caching of results')
    parser.add_argument('--cleanup', action='store_true',
                       help='Clean up old cache files')
    
    args = parser.parse_args()
    
    print("═" * 70)
    print("    ENHANCED AMSTERDAM NOORD FLIGHT ANALYSIS")
    print("    Combining Local Impact + Schiphol Operations")
    print("═" * 70)
    print(f"Mode: {args.mode}")
    print(f"Postal Code: {args.postcode}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Initialize enhanced analyzer
    try:
        analyzer = EnhancedAmsterdamAnalysis(args.postcode)
    except Exception as e:
        print(f"❌ Error initializing analyzer: {e}")
        return
    
    # Handle cleanup if requested
    if args.cleanup:
        print("🧹 Cleaning up old cache files...")
        analyzer.cache.cleanup_old_files()
        print()
    
    # Show cache statistics
    cache_stats = analyzer.cache.get_cache_stats()
    print("CACHE STATUS:")
    print(f"  OpenSky files: {cache_stats['opensky_files']}")
    print(f"  Total cache size: {cache_stats['total_size_mb']} MB")
    print()
    
    # Get flight data based on mode
    local_flights = pd.DataFrame()
    schiphol_flights = pd.DataFrame()
    
    if args.mode == 'cached':
        print("📁 Loading cached data...")
        local_flights = analyzer.cache.load_opensky_data(hours_back=24)
        schiphol_flights = local_flights  # Use same data for cached mode
        
    else:
        # Load credentials and fetch live data
        creds = load_credentials(args.credentials)
        fetcher = OpenSkyFetcher(**creds)
        
        try:
            local_flights, schiphol_flights = analyzer.get_dual_flight_data(fetcher, args.mode)
            
            # Cache the results unless disabled
            if not args.no_cache:
                if not local_flights.empty:
                    analyzer.cache.save_opensky_data(local_flights, f"{args.mode}_local")
                if not schiphol_flights.empty and not schiphol_flights.equals(local_flights):
                    analyzer.cache.save_opensky_data(schiphol_flights, f"{args.mode}_schiphol")
                    
        except Exception as e:
            print(f"❌ Error fetching flight data: {e}")
            return
    
    # Perform comprehensive analysis
    if local_flights.empty and schiphol_flights.empty:
        print("❌ No flight data available for analysis")
        return
    
    print("🧠 Performing enhanced analysis...")
    analysis_results = analyzer.analyze_comprehensive(local_flights, schiphol_flights)
    
    # Generate and display report
    report = analyzer.generate_enhanced_report(analysis_results)
    print(report)
    
    # Save detailed results
    results_file = f"enhanced_analysis_{args.postcode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(analysis_results, f, indent=2, default=str)
    
    print(f"📄 Detailed results saved to: {results_file}")


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