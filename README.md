# Amsterdam Noord Flight Analysis System

Comprehensive flight data collection and analysis system for Amsterdam Noord 1032, focusing on aircraft noise patterns and traffic analysis over residential areas.

## 🎯 Project Overview

This system collects real-time flight data over Amsterdam Noord to analyze:
- Aircraft noise impact on residential areas
- Flight patterns and traffic density
- Schiphol approach/departure corridors over Noord
- Time-based flight activity patterns
- Aircraft classification and noise levels

## 🚀 Features

- **Real-time Data Collection**: Continuous 2-week intensive monitoring
- **Smart Scheduling**: More frequent collection during peak hours (3 min) vs night hours (10 min)
- **Dual Area Coverage**: Local house vicinity + broader Schiphol operations
- **Enhanced Analytics**: Noise impact calculation, distance analysis, pattern detection
- **Production Ready**: Secure deployment with systemd service, log rotation, monitoring

## 📊 Current Status

**Active Data Collection** (as of July 31, 2025):
- ✅ Service running continuously on production server
- ✅ ~380 collections per day (764 API calls within 4000 limit)
- ✅ Comprehensive flight pattern data being gathered
- ✅ 14-day collection period: July 31 - August 14, 2025

## 🔧 Components

### Core Scripts
- `two_week_flight_collector.py` - Main collection service with smart scheduling
- `opensky_fetcher.py` - OpenSky Network API integration with OAuth2
- `schiphol_analyzer.py` - Flight analysis and noise impact calculation
- `amsterdam_flight_analysis.py` - Data analysis and visualization

### Support Files
- `monitor.sh` - Production monitoring script
- `deployment_package/` - Production deployment files
- `DEPLOYMENT_SUMMARY.md` - Deployment status and management

## 📈 Data Analysis

The system generates:
- **Flight Pattern Analysis**: Traffic density maps and time-based patterns
- **Noise Impact Reports**: dB level analysis and high-noise event detection
- **Aircraft Classification**: Type identification and route analysis
- **Interactive Visualizations**: Maps showing flight paths over Noord

## 🛠 Management Commands

**Monitor Status:**
```bash
./monitor.sh
```

**Server Management:**
```bash
# Check service status
ssh linux-server "systemctl status flight-collector"

# View real-time logs
ssh linux-server "journalctl -u flight-collector -f"

# Restart if needed
ssh linux-server "systemctl restart flight-collector"
```

## 🔐 Security

- ✅ Non-root execution with dedicated `flightcollector` user
- ✅ Secure credential storage (600 permissions)
- ✅ SystemD service hardening
- ✅ Network access restrictions
- ✅ File system protections

## 📋 Technical Details

**API Usage**: 764 calls/day (within 4000 OpenSky limit)
**Database**: SQLite with optimized schema for pattern analysis
**Collection Frequency**: 3 min (peak) / 10 min (night)
**Areas Monitored**: Local (1km radius) + Schiphol operations zone
**Data Retention**: Full 2-week dataset for comprehensive analysis

## 🎉 Recent Fixes

**July 31, 2025**: Fixed critical scheduling bug that prevented continuous collection
- Issue: Scheduler clearing jobs before execution
- Fix: Proper one-time job scheduling with auto-rescheduling
- Result: 99.7% improvement in data collection rate (from 1 to 380 collections/day)

## 📄 License

Data collection respects OpenSky Network terms of service. Analysis code available under standard terms.