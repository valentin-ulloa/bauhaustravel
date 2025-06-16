"""
TC-004 Prompt Compression Utility
MVP approach: 40% token reduction without quality loss
"""

import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()

class PromptCompressor:
    """
    Utility class for compressing prompts to reduce token usage.
    
    TC-004 Design Principles:
    - Maintain essential information
    - Reduce verbosity and redundancy
    - Configurable compression levels
    - Preserve prompt effectiveness
    """
    
    @staticmethod
    def compress_conversation_history(conversations: List[Dict]) -> str:
        """
        Compress conversation history to essential exchanges.
        
        Args:
            conversations: List of conversation dictionaries
            
        Returns:
            Compressed conversation string
        """
        if not conversations:
            return ""
        
        # Take only last 3 exchanges (vs original 6)
        recent_conversations = conversations[-6:]  # Last 6 messages = 3 exchanges
        
        if not recent_conversations:
            return ""
        
        # Compact format: USER/BOT abbreviated
        compressed_lines = []
        for conv in recent_conversations:
            sender = "U" if conv["sender"] == "user" else "A"  # User/Assistant
            message = conv["message"][:100]  # Truncate long messages
            if len(conv["message"]) > 100:
                message += "..."
            compressed_lines.append(f"{sender}: {message}")
        
        return "\n".join(compressed_lines)
    
    @staticmethod 
    def compress_trip_info(trip: Dict) -> str:
        """
        Compress trip information to essential format.
        
        Args:
            trip: Trip dictionary with all fields
            
        Returns:
            Compressed trip info string
        """
        # Format: "Name | Flight | Route | Date"
        name = trip.get('client_name', 'Unknown')
        flight = trip.get('flight_number', 'N/A')
        origin = trip.get('origin_iata', '')
        destination = trip.get('destination_iata', '')
        departure = trip.get('departure_date', '')
        
        # Parse date to show only date part
        if isinstance(departure, str) and departure:
            try:
                if 'T' in departure:
                    departure = departure.split('T')[0]  # Just date part
            except:
                pass
        
        route = f"{origin}→{destination}" if origin and destination else "Route TBD"
        
        return f"{name} | {flight} | {route} | {departure}"
    
    @staticmethod
    def compress_context(context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compress complete context to essential fields only.
        
        Args:
            context: Complete conversation context
            
        Returns:
            Compressed context dictionary
        """
        compressed = {
            'trip': {},
            'conversation_history': [],
            'itinerary': None,
            'documents': []
        }
        
        # Compress trip info
        if context.get('trip'):
            trip = context['trip']
            compressed['trip'] = {
                'client_name': trip.get('client_name'),
                'flight_number': trip.get('flight_number'),
                'origin_iata': trip.get('origin_iata'),
                'destination_iata': trip.get('destination_iata'),
                'departure_date': trip.get('departure_date'),
                'client_description': trip.get('client_description', '')[:200]  # Truncate long descriptions
            }
        
        # Compress conversation history (last 3 exchanges)
        if context.get('conversation_history'):
            compressed['conversation_history'] = context['conversation_history'][-6:]
        
        # Compress itinerary (summary only)
        if context.get('itinerary') and context['itinerary'].get('days'):
            days = context['itinerary']['days']
            compressed['itinerary'] = {
                'days_count': len(days),
                'first_day_activities': len(days[0].get('items', [])) if days else 0,
                'has_itinerary': True
            }
        
        # Compress documents (types only)
        if context.get('documents'):
            doc_types = list(set(doc.get('type', 'unknown') for doc in context['documents']))
            compressed['documents'] = doc_types
        
        return compressed
    
    @staticmethod
    def get_compression_ratio(original_text: str, compressed_text: str) -> float:
        """
        Calculate compression ratio between original and compressed text.
        
        Args:
            original_text: Original prompt text
            compressed_text: Compressed prompt text
            
        Returns:
            Compression ratio (percentage reduction)
        """
        original_length = len(original_text.split())
        compressed_length = len(compressed_text.split())
        
        if original_length == 0:
            return 0.0
        
        reduction = (original_length - compressed_length) / original_length
        return reduction * 100
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Estimate token count for text (rough approximation).
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        # Rough estimation: 1 token ≈ 0.75 words
        word_count = len(text.split())
        return int(word_count / 0.75)
    
    @staticmethod
    def should_use_compression() -> bool:
        """
        Check if compression should be used based on environment variables.
        
        Returns:
            True if compression should be used
        """
        return os.getenv("COMPRESS_CONCIERGE_PROMPTS", "false").lower() == "true"
    
    @staticmethod
    def get_target_compression_ratio() -> int:
        """
        Get target compression ratio from environment.
        
        Returns:
            Target compression percentage (default: 40)
        """
        try:
            return int(os.getenv("PROMPT_COMPRESSION_RATIO_TARGET", "40"))
        except ValueError:
            return 40 