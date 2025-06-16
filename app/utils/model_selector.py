"""
TC-004 Smart Model Selection Utility
MVP approach: Simple rules-based complexity scoring for cost optimization
"""

import os
import re
from typing import Dict, Any, Tuple
from enum import Enum
import structlog

logger = structlog.get_logger()

class ModelType(Enum):
    """Available model types with cost implications"""
    GPT_35_TURBO = "gpt-3.5-turbo"      # ~10x cheaper, good for simple queries
    GPT_4O_MINI = "gpt-4o-mini"         # More capable, higher cost

class ComplexityLevel(Enum):
    """Query complexity levels"""
    SIMPLE = "simple"           # Basic info requests, greetings
    MODERATE = "moderate"       # Context-aware responses
    COMPLEX = "complex"         # Multi-step reasoning, creative tasks

class ModelSelector:
    """
    Smart model selection based on query complexity.
    
    TC-004 Design Principles:
    - Simple rules-based scoring (no ML overhead)
    - Conservative approach (prefer quality over cost when uncertain)
    - Easy to tune and debug
    - Cost tracking for optimization
    """
    
    # Cost per 1K tokens (approximate)
    MODEL_COSTS = {
        ModelType.GPT_35_TURBO: 0.0015,   # $0.0015 per 1K tokens
        ModelType.GPT_4O_MINI: 0.015,     # $0.015 per 1K tokens (10x more)
    }
    
    @staticmethod
    def analyze_query_complexity(
        user_message: str,
        context: Dict[str, Any],
        conversation_history: list = None
    ) -> Tuple[ComplexityLevel, Dict[str, Any]]:
        """
        Analyze query complexity to determine appropriate model.
        
        Args:
            user_message: User's current message
            context: Current conversation context
            conversation_history: Recent conversation history
            
        Returns:
            Tuple of (complexity_level, analysis_details)
        """
        analysis = {
            'message_length': len(user_message),
            'word_count': len(user_message.split()),
            'has_questions': '?' in user_message,
            'keywords_found': [],
            'context_complexity': 0,
            'reasoning': []
        }
        
        score = 0
        reasoning = []
        
        # 1. Message length analysis
        word_count = len(user_message.split())
        if word_count > 30:
            score += 2
            reasoning.append(f"Long message ({word_count} words)")
        elif word_count > 15:
            score += 1
            reasoning.append(f"Medium message ({word_count} words)")
        
        # 2. Simple greeting/status patterns (SIMPLE)
        simple_patterns = [
            r'^(hola|hi|hello|buenos días|buenas tardes)',
            r'(cómo está|how is|estado del vuelo|flight status)',
            r'^(gracias|thank you|ok|vale|perfecto)',
            r'(sí|no|yes|no)$'
        ]
        
        message_lower = user_message.lower()
        for pattern in simple_patterns:
            if re.search(pattern, message_lower):
                score -= 2  # Reduce complexity for simple patterns
                reasoning.append(f"Simple pattern detected: {pattern}")
                analysis['keywords_found'].append(pattern)
        
        # 3. Document/info requests (SIMPLE to MODERATE)
        info_patterns = [
            r'(boarding pass|pase de abordar|documento)',
            r'(hotel|reserva|voucher)',
            r'(itinerario|plan|agenda)',
            r'(vuelo|flight|horario)'
        ]
        
        for pattern in info_patterns:
            if re.search(pattern, message_lower):
                score += 0.5  # Slight increase for info requests
                reasoning.append(f"Info request: {pattern}")
                analysis['keywords_found'].append(pattern)
        
        # 4. Complex reasoning indicators (COMPLEX)
        complex_patterns = [
            r'(por qué|why|explain|explica)',
            r'(recomendación|recommendation|suggest|recomienda)',
            r'(comparar|compare|mejor opción|best option)',
            r'(problema|problem|issue|ayuda con)',
            r'(cambiar|modify|update|actualizar)',
            r'(múltiple|varios|different|distintos)'
        ]
        
        for pattern in complex_patterns:
            if re.search(pattern, message_lower):
                score += 2
                reasoning.append(f"Complex reasoning: {pattern}")
                analysis['keywords_found'].append(pattern)
        
        # 5. Context complexity
        context_score = 0
        if context.get('itinerary') and context['itinerary'].get('days'):
            context_score += 1
            reasoning.append("Has itinerary data")
        
        if context.get('documents') and len(context.get('documents', [])) > 2:
            context_score += 1
            reasoning.append("Multiple documents available")
        
        if conversation_history and len(conversation_history) > 4:
            context_score += 1
            reasoning.append("Long conversation history")
        
        score += context_score
        analysis['context_complexity'] = context_score
        
        # 6. Multiple questions (COMPLEX)
        question_count = user_message.count('?')
        if question_count > 1:
            score += 2
            reasoning.append(f"Multiple questions ({question_count})")
        elif question_count == 1:
            score += 0.5
            reasoning.append("Single question")
        
        # 7. Determine complexity level
        if score <= 0:
            complexity = ComplexityLevel.SIMPLE
        elif score <= 3:
            complexity = ComplexityLevel.MODERATE
        else:
            complexity = ComplexityLevel.COMPLEX
        
        analysis['reasoning'] = reasoning
        analysis['complexity_score'] = score
        
        return complexity, analysis
    
    @staticmethod
    def select_model(
        user_message: str,
        context: Dict[str, Any],
        conversation_history: list = None,
        force_model: str = None
    ) -> Tuple[ModelType, Dict[str, Any]]:
        """
        Select appropriate model based on query complexity.
        
        Args:
            user_message: User's current message
            context: Current conversation context
            conversation_history: Recent conversation history
            force_model: Override model selection (for testing)
            
        Returns:
            Tuple of (selected_model, decision_details)
        """
        
        # Check if model selection is enabled
        if not ModelSelector.is_smart_selection_enabled():
            return ModelType.GPT_4O_MINI, {
                'reason': 'Smart selection disabled',
                'complexity': 'unknown',
                'cost_savings': False
            }
        
        # Force model override (for testing)
        if force_model:
            model = ModelType.GPT_35_TURBO if force_model == "gpt-3.5-turbo" else ModelType.GPT_4O_MINI
            return model, {
                'reason': f'Forced model: {force_model}',
                'complexity': 'override',
                'cost_savings': model == ModelType.GPT_35_TURBO
            }
        
        # Analyze complexity
        complexity, analysis = ModelSelector.analyze_query_complexity(
            user_message, context, conversation_history
        )
        
        # Model selection logic
        if complexity == ComplexityLevel.SIMPLE:
            selected_model = ModelType.GPT_35_TURBO
            reason = "Simple query - cost optimization"
        elif complexity == ComplexityLevel.MODERATE:
            # Check if we have enough context for GPT-3.5
            if analysis['context_complexity'] <= 1:
                selected_model = ModelType.GPT_35_TURBO
                reason = "Moderate query with simple context"
            else:
                selected_model = ModelType.GPT_4O_MINI
                reason = "Moderate query with complex context"
        else:  # COMPLEX
            selected_model = ModelType.GPT_4O_MINI
            reason = "Complex query - quality prioritized"
        
        decision_details = {
            'complexity': complexity.value,
            'complexity_score': analysis['complexity_score'],
            'reason': reason,
            'analysis': analysis,
            'cost_savings': selected_model == ModelType.GPT_35_TURBO,
            'estimated_cost_ratio': ModelSelector.MODEL_COSTS[selected_model] / ModelSelector.MODEL_COSTS[ModelType.GPT_4O_MINI]
        }
        
        logger.info("model_selection_decision",
            model=selected_model.value,
            complexity=complexity.value,
            score=analysis['complexity_score'],
            reason=reason,
            cost_savings=decision_details['cost_savings']
        )
        
        return selected_model, decision_details
    
    @staticmethod
    def is_smart_selection_enabled() -> bool:
        """Check if smart model selection is enabled via environment."""
        return os.getenv("ENABLE_SMART_MODEL_SELECTION", "false").lower() == "true"
    
    @staticmethod
    def get_cost_savings_threshold() -> float:
        """Get minimum complexity score required for GPT-4o (higher = more aggressive savings)."""
        try:
            return float(os.getenv("MODEL_SELECTION_THRESHOLD", "2.0"))
        except ValueError:
            return 2.0
    
    @staticmethod
    def estimate_cost_savings(
        total_tokens: int,
        model_used: ModelType,
        baseline_model: ModelType = ModelType.GPT_4O_MINI
    ) -> Dict[str, float]:
        """
        Estimate cost savings from model selection.
        
        Args:
            total_tokens: Total tokens used in the request
            model_used: Model that was actually used
            baseline_model: Model that would have been used by default
            
        Returns:
            Cost analysis dictionary
        """
        baseline_cost = (total_tokens / 1000) * ModelSelector.MODEL_COSTS[baseline_model]
        actual_cost = (total_tokens / 1000) * ModelSelector.MODEL_COSTS[model_used]
        savings = baseline_cost - actual_cost
        savings_percentage = (savings / baseline_cost * 100) if baseline_cost > 0 else 0
        
        return {
            'baseline_cost': baseline_cost,
            'actual_cost': actual_cost,
            'savings_amount': savings,
            'savings_percentage': savings_percentage,
            'tokens_used': total_tokens
        } 