"""
Flight data analysis and EDA for Amsterdam Noord
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import folium
from folium import plugins
import os
from pathlib import Path


class FlightAnalyzer:
    """Exploratory Data Analysis for flight patterns over Amsterdam Noord"""
    
    def __init__(self, cache_dir: str = "flight_cache"):
        """
        Initialize flight analyzer
        
        Args:
            cache_dir: Directory for caching processed data
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # Amsterdam Noord center for maps
        self.center_lat = 52.40
        self.center_lon = 4.90
        
    def analyze_flight_patterns(self, df: pd.DataFrame) -> dict:
        """
        Perform comprehensive EDA on flight data
        
        Args:
            df: DataFrame with flight data
            
        Returns:
            Dictionary with analysis results
        """
        if df.empty:
            return {"error": "No flight data to analyze"}
            
        analysis = {}
        
        # Basic statistics
        analysis['total_flights'] = len(df)
        analysis['unique_aircraft'] = df['icao24'].nunique()
        analysis['countries'] = df['origin_country'].value_counts().to_dict()
        analysis['aircraft_types'] = df['aircraft_type'].value_counts().to_dict()
        
        # Altitude analysis
        if 'baro_altitude' in df.columns:
            alt_data = df['baro_altitude'].dropna()
            if not alt_data.empty:
                analysis['altitude_stats'] = {
                    'mean': alt_data.mean(),
                    'median': alt_data.median(),
                    'min': alt_data.min(),
                    'max': alt_data.max(),
                    'std': alt_data.std()
                }
                
                # Low altitude flights (potentially interesting for noise analysis)
                low_alt_threshold = 3000  # feet
                analysis['low_altitude_flights'] = len(alt_data[alt_data < low_alt_threshold])
                analysis['low_altitude_percentage'] = (analysis['low_altitude_flights'] / len(alt_data)) * 100
        
        # Speed analysis
        if 'velocity' in df.columns:
            speed_data = df['velocity'].dropna()
            if not speed_data.empty:
                analysis['speed_stats'] = {
                    'mean_knots': speed_data.mean(),
                    'median_knots': speed_data.median(),
                    'min_knots': speed_data.min(),
                    'max_knots': speed_data.max()
                }
        
        # Time-based analysis
        if 'data_time' in df.columns:
            df['hour'] = pd.to_datetime(df['data_time']).dt.hour
            analysis['hourly_distribution'] = df['hour'].value_counts().sort_index().to_dict()
        
        return analysis
    
    def create_flight_map(self, df: pd.DataFrame, save_path: str = None) -> folium.Map:
        """
        Create interactive map of flight positions
        
        Args:
            df: DataFrame with flight data
            save_path: Optional path to save HTML map
            
        Returns:
            Folium map object
        """
        # Create base map centered on Amsterdam Noord
        m = folium.Map(
            location=[self.center_lat, self.center_lon],
            zoom_start=12,
            tiles='OpenStreetMap'
        )
        
        if df.empty:
            return m
            
        # Add Amsterdam Noord boundary box
        folium.Rectangle(
            bounds=[[52.35, 4.85], [52.45, 4.95]],
            color='red',
            fill=False,
            weight=2,
            popup='Amsterdam Noord Analysis Area'
        ).add_to(m)
        
        # Color code by aircraft type
        colors = {'Commercial': 'blue', 'Private/General Aviation': 'red', 'Other': 'green', 'Unknown': 'gray'}
        
        # Add flight positions
        for idx, row in df.iterrows():
            if pd.notna(row['latitude']) and pd.notna(row['longitude']):
                color = colors.get(row.get('aircraft_type', 'Unknown'), 'gray')
                
                popup_text = f"""
                <b>Callsign:</b> {row.get('callsign', 'Unknown')}<br>
                <b>Country:</b> {row.get('origin_country', 'Unknown')}<br>
                <b>Altitude:</b> {row.get('baro_altitude', 'Unknown')} ft<br>
                <b>Speed:</b> {row.get('velocity', 'Unknown')} knots<br>
                <b>Type:</b> {row.get('aircraft_type', 'Unknown')}
                """
                
                folium.CircleMarker(
                    location=[row['latitude'], row['longitude']],
                    radius=5,
                    popup=popup_text,
                    color=color,
                    fillColor=color,
                    fillOpacity=0.7
                ).add_to(m)
        
        # Add legend
        legend_html = '''
        <div style="position: fixed; 
                    bottom: 50px; left: 50px; width: 200px; height: 120px; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px">
        <p><b>Aircraft Types</b></p>
        <p><i class="fa fa-circle" style="color:blue"></i> Commercial</p>
        <p><i class="fa fa-circle" style="color:red"></i> Private/General Aviation</p>
        <p><i class="fa fa-circle" style="color:green"></i> Other</p>
        <p><i class="fa fa-circle" style="color:gray"></i> Unknown</p>
        </div>
        '''
        m.get_root().html.add_child(folium.Element(legend_html))
        
        if save_path:
            m.save(save_path)
            print(f"Map saved to {save_path}")
            
        return m
    
    def plot_altitude_distribution(self, df: pd.DataFrame, save_path: str = None):
        """Plot altitude distribution of flights"""
        plt.figure(figsize=(12, 6))
        
        if df.empty or 'baro_altitude' not in df.columns:
            plt.text(0.5, 0.5, 'No altitude data available', 
                    transform=plt.gca().transAxes, ha='center', va='center')
            plt.title('Altitude Distribution - No Data')
            if save_path:
                plt.savefig(save_path)
            plt.show()
            return
            
        alt_data = df['baro_altitude'].dropna()
        
        if alt_data.empty:
            plt.text(0.5, 0.5, 'No valid altitude data', 
                    transform=plt.gca().transAxes, ha='center', va='center')
            plt.title('Altitude Distribution - No Valid Data')
            if save_path:
                plt.savefig(save_path)
            plt.show()
            return
        
        # Subplot 1: Histogram
        plt.subplot(1, 2, 1)
        plt.hist(alt_data, bins=30, alpha=0.7, edgecolor='black')
        plt.xlabel('Altitude (feet)')
        plt.ylabel('Number of Aircraft')
        plt.title('Altitude Distribution')
        plt.grid(True, alpha=0.3)
        
        # Subplot 2: Box plot by aircraft type
        plt.subplot(1, 2, 2)
        if 'aircraft_type' in df.columns:
            alt_by_type = df[['baro_altitude', 'aircraft_type']].dropna()
            if not alt_by_type.empty:
                sns.boxplot(data=alt_by_type, x='aircraft_type', y='baro_altitude')
                plt.xticks(rotation=45)
                plt.xlabel('Aircraft Type')
                plt.ylabel('Altitude (feet)')
                plt.title('Altitude by Aircraft Type')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Altitude plot saved to {save_path}")
            
        plt.show()
    
    def plot_time_patterns(self, df: pd.DataFrame, save_path: str = None):
        """Plot flight patterns over time"""
        if df.empty or 'data_time' not in df.columns:
            print("No time data available for plotting")
            return
            
        df_time = df.copy()
        df_time['data_time'] = pd.to_datetime(df_time['data_time'])
        df_time['hour'] = df_time['data_time'].dt.hour
        df_time['minute'] = df_time['data_time'].dt.minute
        
        plt.figure(figsize=(15, 8))
        
        # Plot 1: Hourly distribution
        plt.subplot(2, 2, 1)
        hourly_counts = df_time['hour'].value_counts().sort_index()
        plt.bar(hourly_counts.index, hourly_counts.values)
        plt.xlabel('Hour of Day')
        plt.ylabel('Number of Aircraft')
        plt.title('Aircraft Count by Hour')
        plt.grid(True, alpha=0.3)
        
        # Plot 2: Aircraft type distribution
        plt.subplot(2, 2, 2)
        if 'aircraft_type' in df_time.columns:
            type_counts = df_time['aircraft_type'].value_counts()
            plt.pie(type_counts.values, labels=type_counts.index, autopct='%1.1f%%')
            plt.title('Aircraft Type Distribution')
        
        # Plot 3: Country distribution (top 10)
        plt.subplot(2, 2, 3)
        if 'origin_country' in df_time.columns:
            country_counts = df_time['origin_country'].value_counts().head(10)
            plt.barh(range(len(country_counts)), country_counts.values)
            plt.yticks(range(len(country_counts)), country_counts.index)
            plt.xlabel('Number of Aircraft')
            plt.title('Top 10 Origin Countries')
            plt.grid(True, alpha=0.3)
        
        # Plot 4: Speed vs Altitude scatter
        plt.subplot(2, 2, 4)
        if 'velocity' in df_time.columns and 'baro_altitude' in df_time.columns:
            scatter_data = df_time[['velocity', 'baro_altitude', 'aircraft_type']].dropna()
            if not scatter_data.empty:
                for aircraft_type in scatter_data['aircraft_type'].unique():
                    type_data = scatter_data[scatter_data['aircraft_type'] == aircraft_type]
                    plt.scatter(type_data['velocity'], type_data['baro_altitude'], 
                              label=aircraft_type, alpha=0.6)
                plt.xlabel('Speed (knots)')
                plt.ylabel('Altitude (feet)')
                plt.title('Speed vs Altitude')
                plt.legend()
                plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Time patterns plot saved to {save_path}")
            
        plt.show()
    
    def generate_report(self, df: pd.DataFrame) -> str:
        """Generate text report of analysis"""
        analysis = self.analyze_flight_patterns(df)
        
        if 'error' in analysis:
            return f"Analysis Error: {analysis['error']}"
        
        report = f"""
        AMSTERDAM NOORD FLIGHT ANALYSIS REPORT
        =====================================
        Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        OVERVIEW:
        - Total aircraft detected: {analysis['total_flights']}
        - Unique aircraft: {analysis['unique_aircraft']}
        
        AIRCRAFT TYPES:
        """
        
        for aircraft_type, count in analysis['aircraft_types'].items():
            percentage = (count / analysis['total_flights']) * 100
            report += f"- {aircraft_type}: {count} ({percentage:.1f}%)\n        "
        
        if 'altitude_stats' in analysis:
            report += f"""
        ALTITUDE ANALYSIS:
        - Average altitude: {analysis['altitude_stats']['mean']:.0f} feet
        - Median altitude: {analysis['altitude_stats']['median']:.0f} feet
        - Altitude range: {analysis['altitude_stats']['min']:.0f} - {analysis['altitude_stats']['max']:.0f} feet
        - Low altitude flights (<3000ft): {analysis['low_altitude_flights']} ({analysis['low_altitude_percentage']:.1f}%)
        """
        
        if 'speed_stats' in analysis:
            report += f"""
        SPEED ANALYSIS:
        - Average speed: {analysis['speed_stats']['mean_knots']:.0f} knots
        - Speed range: {analysis['speed_stats']['min_knots']:.0f} - {analysis['speed_stats']['max_knots']:.0f} knots
        """
        
        report += f"""
        TOP ORIGIN COUNTRIES:
        """
        for country, count in list(analysis['countries'].items())[:5]:
            report += f"- {country}: {count}\n        "
        
        return report


if __name__ == "__main__":
    # Test the analyzer with sample data
    analyzer = FlightAnalyzer()
    
    # Create sample data for testing
    sample_data = pd.DataFrame({
        'icao24': ['abc123', 'def456', 'ghi789'],
        'callsign': ['KLM123', 'TRA456', 'PVT789'],
        'origin_country': ['Netherlands', 'Germany', 'Belgium'],
        'latitude': [52.40, 52.41, 52.39],
        'longitude': [4.90, 4.91, 4.89],
        'baro_altitude': [2000, 15000, 8000],
        'velocity': [150, 450, 200],
        'aircraft_type': ['Commercial', 'Commercial', 'Private/General Aviation'],
        'data_time': pd.Timestamp.now()
    })
    
    print("Testing FlightAnalyzer with sample data...")
    report = analyzer.generate_report(sample_data)
    print(report)