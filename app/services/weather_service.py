"""Weather service for Bauhaus Travel - provides real weather data for flight notifications."""

import os
import asyncio
from typing import Dict, Optional
from datetime import datetime, timezone
import httpx
import structlog

logger = structlog.get_logger()


class WeatherService:
    """Service for fetching real weather data for airports."""
    
    def __init__(self):
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        self.base_url = "https://api.openweathermap.org/data/2.5"
        
        # Cache to avoid repeated API calls for same airport
        self._weather_cache: Dict[str, Dict] = {}
        self._cache_duration_minutes = 30  # Cache weather for 30 minutes
        
        if not self.api_key:
            logger.warning("openweather_api_key_missing", 
                message="OPENWEATHER_API_KEY not set - using fallback weather text")
    
    async def get_weather_for_destination(self, destination_iata: str) -> str:
        """
        Get weather description for destination airport.
        
        Args:
            destination_iata: Destination airport IATA code (e.g., 'GUA', 'LGA')
            
        Returns:
            Human-readable weather description in Spanish for notifications
        """
        if not self.api_key:
            return self._get_fallback_weather()
        
        try:
            # Check cache first
            cache_key = f"weather_{destination_iata}"
            if self._is_cache_valid(cache_key):
                cached_weather = self._weather_cache[cache_key]
                return self._format_weather_spanish(cached_weather)
            
            # Get airport coordinates (simplified mapping - in production would use airport API)
            airport_coords = self._get_airport_coordinates(destination_iata)
            if not airport_coords:
                logger.warning("airport_coordinates_not_found", 
                    iata=destination_iata)
                return self._get_fallback_weather()
            
            # Fetch current weather
            weather_data = await self._fetch_weather_data(
                airport_coords["lat"], 
                airport_coords["lon"]
            )
            
            if weather_data:
                # Cache the result
                self._weather_cache[cache_key] = {
                    "data": weather_data,
                    "timestamp": datetime.now(timezone.utc),
                    "iata": destination_iata
                }
                
                return self._format_weather_spanish(self._weather_cache[cache_key])
            else:
                return self._get_fallback_weather()
                
        except Exception as e:
            logger.error("weather_fetch_failed", 
                destination_iata=destination_iata,
                error=str(e)
            )
            return self._get_fallback_weather()
    
    async def _fetch_weather_data(self, lat: float, lon: float) -> Optional[Dict]:
        """Fetch weather data from OpenWeatherMap API."""
        try:
            params = {
                "lat": lat,
                "lon": lon,
                "appid": self.api_key,
                "units": "metric",  # Celsius
                "lang": "es"  # Spanish descriptions
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/weather", params=params)
                response.raise_for_status()
                
                weather_data = response.json()
                
                logger.info("weather_data_fetched", 
                    lat=lat,
                    lon=lon,
                    weather=weather_data.get("weather", [{}])[0].get("description", "unknown"),
                    temperature=weather_data.get("main", {}).get("temp", "unknown")
                )
                
                return weather_data
                
        except Exception as e:
            logger.error("openweather_api_failed", 
                lat=lat,
                lon=lon,
                error=str(e)
            )
            return None
    
    def _format_weather_spanish(self, cached_entry: Dict) -> str:
        """Format weather data into Spanish notification text."""
        weather_data = cached_entry["data"]
        
        try:
            # Extract weather info
            weather_desc = weather_data.get("weather", [{}])[0].get("description", "buen clima")
            temp = weather_data.get("main", {}).get("temp")
            
            # Create notification text
            if temp is not None:
                temp_str = f"{int(temp)}°C"
                return f"{weather_desc} ({temp_str})"
            else:
                return weather_desc
                
        except (KeyError, IndexError, TypeError) as e:
            logger.warning("weather_format_failed", 
                error=str(e),
                data=weather_data
            )
            return self._get_fallback_weather()
    
    def _get_airport_coordinates(self, iata: str) -> Optional[Dict[str, float]]:
        """
        Get airport coordinates by IATA code.
        
        In production, this would use a comprehensive airport database API.
        For now, using a subset of major airports.
        """
        # Major airports coordinates (subset for demo)
        airport_coords = {
            # Americas
            "MIA": {"lat": 25.7959, "lon": -80.2870},  # Miami
            "JFK": {"lat": 40.6413, "lon": -73.7781},  # New York JFK
            "LAX": {"lat": 33.9425, "lon": -118.4081}, # Los Angeles
            "EZE": {"lat": -34.8222, "lon": -58.5358}, # Buenos Aires
            "GUA": {"lat": 14.5833, "lon": -90.5275}, # Guatemala City
            "BOG": {"lat": 4.7016, "lon": -74.1469},  # Bogotá
            "LIM": {"lat": -12.0219, "lon": -77.1143}, # Lima
            "SCL": {"lat": -33.3927, "lon": -70.7854}, # Santiago
            
            # Europe
            "LHR": {"lat": 51.4700, "lon": -0.4543},  # London Heathrow
            "CDG": {"lat": 49.0097, "lon": 2.5479},   # Paris Charles de Gaulle
            "FRA": {"lat": 50.0379, "lon": 8.5622},   # Frankfurt
            "MAD": {"lat": 40.4719, "lon": -3.5626},  # Madrid
            "FCO": {"lat": 41.8003, "lon": 12.2389},  # Rome
            
            # Asia
            "NRT": {"lat": 35.7720, "lon": 140.3929}, # Tokyo Narita
            "ICN": {"lat": 37.4602, "lon": 126.4407}, # Seoul Incheon
            "SIN": {"lat": 1.3644, "lon": 103.9915},  # Singapore
            
            # Add more as needed
        }
        
        return airport_coords.get(iata.upper())
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached weather data is still valid."""
        if cache_key not in self._weather_cache:
            return False
        
        cache_entry = self._weather_cache[cache_key]
        cache_time = cache_entry["timestamp"]
        now = datetime.now(timezone.utc)
        
        age_minutes = (now - cache_time).total_seconds() / 60
        return age_minutes < self._cache_duration_minutes
    
    def _get_fallback_weather(self) -> str:
        """Get fallback weather text when API is unavailable."""
        return "buen clima para volar"
    
    def get_cache_stats(self) -> Dict:
        """Get weather cache statistics for monitoring."""
        return {
            "cache_size": len(self._weather_cache),
            "cache_duration_minutes": self._cache_duration_minutes,
            "api_available": self.api_key is not None
        } 