"""ItineraryAgent for Bauhaus Travel - generates personalized itineraries."""

import os
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID
import structlog
from openai import OpenAI

from ..db.supabase_client import SupabaseDBClient
from ..models.database import Trip, DatabaseResult, AgencyPlace
from .notifications_agent import NotificationsAgent
from .notifications_templates import NotificationType
# TC-004: Import retry logic
from ..utils.retry_logic import retry_async, RetryConfigs

logger = structlog.get_logger()


class ItineraryAgent:
    """
    Autonomous agent for itinerary generation.
    
    Handles:
    - Loading trip + profile (client_description) + agency_places
    - Generating personalized itinerary via GPT-4o mini
    - Validating places against agency_places (source="agency" vs "low_validation")
    - Saving parsed_itinerary to database
    - Sending WhatsApp notification when ready
    """
    
    def __init__(self):
        """Initialize the ItineraryAgent with required services."""
        self.db_client = SupabaseDBClient()
        
        # OpenAI setup
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set in environment variables")
        
        self.openai_client = OpenAI(api_key=openai_api_key)
        
        logger.info("itinerary_agent_initialized")
    
    async def run(self, trip_id: UUID) -> DatabaseResult:
        """
        Main entry point for the ItineraryAgent.
        
        Args:
            trip_id: UUID of the trip to generate itinerary for
            
        Returns:
            DatabaseResult with itinerary generation status
        """
        logger.info("itinerary_generation_requested", trip_id=str(trip_id))
        
        try:
            # Step 1: Load trip data
            trip_result = await self.db_client.get_trip_by_id(trip_id)
            if not trip_result.success:
                error_msg = f"Failed to load trip {trip_id}: {trip_result.error}"
                logger.error("trip_load_failed", trip_id=str(trip_id), error=trip_result.error)
                return DatabaseResult(success=False, error=error_msg)
            
            trip_data = trip_result.data
            trip = Trip(**trip_data)
            
            # Step 2: Load agency places if agency_id is present
            agency_places = []
            if trip.agency_id:
                agency_places = await self.db_client.get_agency_places(
                    agency_id=trip.agency_id,
                    destination_city=None  # TODO: Map IATA codes to cities if needed
                )
                logger.info("agency_places_loaded", 
                    trip_id=str(trip_id),
                    agency_id=str(trip.agency_id),
                    count=len(agency_places)
                )
            
            # Step 3: Build prompt and generate itinerary
            raw_prompt = self.build_prompt(trip, agency_places)
            
            logger.info("generating_itinerary_with_openai", 
                trip_id=str(trip_id),
                prompt_length=len(raw_prompt)
            )
            
            raw_response = await self.call_openai(raw_prompt)
            
            # Step 4: Parse and validate itinerary
            parsed_itinerary = self.parse_and_validate_response(raw_response, agency_places)
            
            # Step 5: Save to database
            itinerary_data = {
                "trip_id": str(trip_id),
                "version": 1,
                "status": "draft",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "raw_prompt": raw_prompt,
                "raw_response": raw_response,
                "parsed_itinerary": parsed_itinerary
            }
            
            create_result = await self.db_client.create_itinerary(itinerary_data)
            if not create_result.success:
                error_msg = f"Failed to save itinerary: {create_result.error}"
                logger.error("itinerary_save_failed", trip_id=str(trip_id), error=create_result.error)
                return DatabaseResult(success=False, error=error_msg)
            
            itinerary_id = create_result.data["id"]
            
            # Step 6: Send WhatsApp notification
            notifications_agent = NotificationsAgent()
            try:
                notification_result = await notifications_agent.send_single_notification(
                    trip_id=str(trip_id),
                    notification_type=NotificationType.ITINERARY_READY
                )
                
                if notification_result.success:
                    logger.info("itinerary_notification_sent", 
                        trip_id=str(trip_id),
                        itinerary_id=itinerary_id
                    )
                else:
                    logger.warning("itinerary_notification_failed", 
                        trip_id=str(trip_id),
                        error=notification_result.error
                    )
            finally:
                await notifications_agent.close()
            
            logger.info("itinerary_generation_completed", 
                trip_id=str(trip_id),
                itinerary_id=itinerary_id,
                days_count=len(parsed_itinerary.get("days", []))
            )
            
            return DatabaseResult(
                success=True,
                data={"itinerary_id": str(itinerary_id), "trip_id": str(trip_id)},
                affected_rows=1
            )
            
        except Exception as e:
            logger.error("itinerary_generation_failed", 
                trip_id=str(trip_id),
                error=str(e)
            )
            return DatabaseResult(success=False, error=str(e))
    
    def build_prompt(self, trip: Trip, agency_places: List[AgencyPlace]) -> str:
        """
        Build personalized prompt for itinerary generation.
        
        Args:
            trip: Trip object with flight and profile data
            agency_places: List of validated agency places
            
        Returns:
            Complete prompt string for OpenAI
        """
        # Calculate trip duration (simple estimation based on departure date)
        # TODO: Add return date when available
        trip_duration = 3  # Default to 3 days for MVP
        
        # Format agency places for prompt
        agency_places_text = ""
        if agency_places:
            places_list = []
            for place in agency_places:
                place_info = f"- {place.name}"
                if place.address:
                    place_info += f" ({place.address})"
                if place.type:
                    place_info += f" - {place.type}"
                places_list.append(place_info)
            
            agency_places_text = f"""

PREFERRED PLACES (validated by travel agency):
{chr(10).join(places_list)}

These places are verified and preferred. Include them when relevant to the itinerary.
"""

        prompt = f"""You are a travel expert creating a personalized day-by-day itinerary.

TRIP DETAILS:
- Traveler: {trip.client_name}
- Destination: {trip.destination_iata} (from {trip.origin_iata})
- Flight: {trip.flight_number}
- Departure: {trip.departure_date.strftime('%Y-%m-%d %H:%M')}
- Duration: {trip_duration} days

TRAVELER PROFILE:
{trip.client_description or "No specific preferences provided"}

{agency_places_text}

INSTRUCTIONS:
1. Create a {trip_duration}-day itinerary starting from arrival
2. Include specific places with addresses when possible
3. Consider the traveler's profile and preferences
4. Mix must-see attractions with local experiences
5. Include practical details (opening hours, approximate costs)
6. Add safety tips if relevant

FORMAT YOUR RESPONSE AS JSON:
{{
  "days": [
    {{
      "date": "YYYY-MM-DD",
      "items": [
        {{
          "title": "Place/Activity Name",
          "type": "restaurant|attraction|hotel|activity|transport",
          "address": "Full address if available",
          "city": "{trip.destination_iata}",
          "country": "Country name",
          "lat": null,
          "lng": null,
          "opening_hours": "Hours or null",
          "rating": null,
          "source": "low_validation",
          "safety_warnings": [],
          "tags": ["tag1", "tag2"]
        }}
      ]
    }}
  ]
}}

Make it personal and exciting for {trip.client_name}!"""

        return prompt
    
    async def call_openai(self, prompt: str) -> str:
        """
        Call OpenAI API to generate itinerary.
        
        Args:
            prompt: Complete prompt string
            
        Returns:
            Raw response from OpenAI
        """
        try:
            # TC-004: Use retry logic for robust OpenAI calls
            response = await retry_async(
                lambda: self._make_openai_request(prompt),
                config=RetryConfigs.OPENAI_API,
                context="itinerary_generation"
            )
            
            raw_response = response.choices[0].message.content
            
            logger.info("openai_response_received", 
                tokens_used=response.usage.total_tokens,
                response_length=len(raw_response)
            )
            
            return raw_response
            
        except Exception as e:
            logger.error("openai_call_failed", error=str(e))
            raise e
    
    async def _make_openai_request(self, prompt: str):
        """
        TC-004: Extracted method for making OpenAI requests (for retry logic).
        """
        # Convert sync OpenAI call to async context
        import asyncio
        
        def sync_openai_call():
            return self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional travel planner. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, sync_openai_call)
    
    def parse_and_validate_response(self, raw_response: str, agency_places: List[AgencyPlace]) -> dict:
        """
        Parse OpenAI response and validate places against agency_places.
        
        Args:
            raw_response: Raw JSON response from OpenAI
            agency_places: List of validated agency places
            
        Returns:
            Parsed and validated itinerary dict
        """
        try:
            # Parse JSON response
            parsed_itinerary = json.loads(raw_response)
            
            # Validate structure
            if "days" not in parsed_itinerary:
                raise ValueError("Invalid itinerary format: missing 'days' field")
            
            # Define allowed values for validation
            allowed_sources = ["agency", "low_validation"]
            allowed_types = ["restaurant", "attraction", "hotel", "activity", "transport", "other"]
            
            # Create agency places lookup for validation
            agency_lookup = {}
            for place in agency_places:
                # Create multiple lookup keys for flexible matching
                keys = [
                    place.name.lower(),
                    f"{place.name.lower()} {place.city.lower()}".strip()
                ]
                if place.address:
                    keys.append(f"{place.name.lower()} {place.address.lower()}".strip())
                
                for key in keys:
                    agency_lookup[key] = place
            
            # Validate and normalize all items
            for day in parsed_itinerary["days"]:
                if "items" not in day:
                    day["items"] = []  # Ensure items exists
                    continue
                
                for item in day["items"]:
                    # Normalize and validate required fields
                    item["title"] = str(item.get("title") or "Unnamed Activity").strip()
                    
                    # Normalize type field
                    item_type = (item.get("type") or "").lower().strip()
                    item["type"] = item_type if item_type in allowed_types else "other"
                    
                    # Normalize address, city, country
                    item["address"] = str(item.get("address") or "").strip()
                    item["city"] = str(item.get("city") or "").strip()
                    item["country"] = str(item.get("country") or "").strip()
                    
                    # Handle coordinates safely
                    try:
                        item["lat"] = float(item["lat"]) if item.get("lat") is not None else None
                    except (ValueError, TypeError):
                        item["lat"] = None
                    
                    try:
                        item["lng"] = float(item["lng"]) if item.get("lng") is not None else None
                    except (ValueError, TypeError):
                        item["lng"] = None
                    
                    # Handle rating safely
                    try:
                        item["rating"] = float(item["rating"]) if item.get("rating") is not None else None
                    except (ValueError, TypeError):
                        item["rating"] = None
                    
                    # Normalize opening_hours
                    item["opening_hours"] = str(item.get("opening_hours") or "").strip() or None
                    
                    # Ensure safety_warnings and tags are lists
                    item["safety_warnings"] = item.get("safety_warnings") or []
                    if not isinstance(item["safety_warnings"], list):
                        item["safety_warnings"] = []
                    
                    item["tags"] = item.get("tags") or []
                    if not isinstance(item["tags"], list):
                        item["tags"] = []
                    
                    # Normalize and validate source field
                    source = (item.get("source") or "").lower().strip()
                    if source not in allowed_sources:
                        source = "low_validation"  # Default fallback
                    
                    # Check if this item matches any agency place (only if we have agency places)
                    if agency_places:
                        item_name = item["title"].lower()
                        item_address = item["address"].lower()
                        
                        # Try different matching strategies
                        match_keys = [
                            item_name,
                            f"{item_name} {item['city'].lower()}".strip(),
                            f"{item_name} {item_address}".strip()
                        ]
                        
                        matched = False
                        for key in match_keys:
                            if key in agency_lookup:
                                agency_place = agency_lookup[key]
                                source = "agency"  # Override with agency validation
                                
                                # Enhance with agency data
                                if agency_place.lat and agency_place.lng:
                                    item["lat"] = agency_place.lat
                                    item["lng"] = agency_place.lng
                                if agency_place.rating:
                                    item["rating"] = agency_place.rating
                                if agency_place.opening_hours:
                                    item["opening_hours"] = agency_place.opening_hours
                                matched = True
                                break
                    
                    # Set final validated source
                    item["source"] = source
            
            logger.info("itinerary_parsed_and_validated", 
                days_count=len(parsed_itinerary["days"]),
                total_items=sum(len(day.get("items", [])) for day in parsed_itinerary["days"]),
                agency_matches=sum(1 for day in parsed_itinerary["days"] 
                                 for item in day.get("items", []) 
                                 if item.get("source") == "agency")
            )
            
            return parsed_itinerary
            
        except json.JSONDecodeError as e:
            logger.error("json_parse_failed", error=str(e), raw_response=raw_response[:500])
            # Return a basic fallback structure
            return {
                "days": [
                    {
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "items": [
                            {
                                "title": "Itinerary generation failed",
                                "type": "error",
                                "address": "",
                                "city": "",
                                "country": "",
                                "lat": None,
                                "lng": None,
                                "opening_hours": None,
                                "rating": None,
                                "source": "low_validation",
                                "safety_warnings": ["Please contact support"],
                                "tags": ["error"]
                            }
                        ]
                    }
                ]
            }
        
        except Exception as e:
            logger.error("itinerary_validation_failed", error=str(e))
            raise e
    
    async def close(self):
        """Clean up resources."""
        await self.db_client.close()
        logger.info("itinerary_agent_closed") 