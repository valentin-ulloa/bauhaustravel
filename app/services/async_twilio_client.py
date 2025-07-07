"""
Async Twilio client using httpx instead of blocking SDK.

This module provides non-blocking HTTP calls to Twilio's API, preventing
event loop stalls in the NotificationsAgent.
"""

import httpx
import base64
import json
import structlog
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = structlog.get_logger()


@dataclass
class TwilioMessage:
    """Result of a Twilio API call."""
    sid: str
    status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class AsyncTwilioClient:
    """
    Async Twilio client using httpx instead of blocking SDK.
    
    Provides non-blocking HTTP calls to Twilio's Messages API for:
    - WhatsApp template messages (content_sid)
    - Simple text messages (body)
    - Media messages (media_url)
    
    Usage:
        client = AsyncTwilioClient(account_sid, auth_token)
        result = await client.send_template_message(...)
    """
    
    def __init__(self, account_sid: str, auth_token: str):
        """
        Initialize async Twilio client.
        
        Args:
            account_sid: Twilio Account SID
            auth_token: Twilio Auth Token
        """
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}"
        
        # Create Basic Auth header
        auth_string = f"{account_sid}:{auth_token}"
        auth_bytes = auth_string.encode('ascii')
        auth_header = base64.b64encode(auth_bytes).decode('ascii')
        
        self.headers = {
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Bauhaus-Travel-AsyncClient/1.0"
        }
        
        logger.info("async_twilio_client_initialized", 
            account_sid=account_sid[:8] + "...",
            base_url=self.base_url
        )
    
    async def send_template_message(
        self,
        to: str,
        messaging_service_sid: str,
        content_sid: str,
        content_variables: Dict[str, Any]
    ) -> TwilioMessage:
        """
        Send WhatsApp template message using Twilio Content API.
        
        Args:
            to: Phone number with whatsapp: prefix
            messaging_service_sid: Twilio Messaging Service SID
            content_sid: Twilio Content Template SID (HX...)
            content_variables: Template variables as dict
            
        Returns:
            TwilioMessage with result
        """
        data = {
            "To": to,
            "MessagingServiceSid": messaging_service_sid,
            "ContentSid": content_sid,
            "ContentVariables": json.dumps(content_variables)
        }
        
        logger.info("sending_template_message",
            to=to,
            content_sid=content_sid,
            variables_count=len(content_variables)
        )
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/Messages.json",
                    headers=self.headers,
                    data=data
                )
                
                response_data = response.json()
                
                if response.status_code == 201:
                    logger.info("template_message_sent_successfully",
                        message_sid=response_data["sid"],
                        status=response_data["status"],
                        to=to
                    )
                    return TwilioMessage(
                        sid=response_data["sid"],
                        status=response_data["status"]
                    )
                else:
                    logger.error("template_message_send_failed",
                        status_code=response.status_code,
                        error_code=response_data.get("code"),
                        error_message=response_data.get("message"),
                        to=to
                    )
                    return TwilioMessage(
                        sid="",
                        status="failed",
                        error_code=str(response_data.get("code", response.status_code)),
                        error_message=response_data.get("message", "Unknown error")
                    )
                    
        except httpx.TimeoutException:
            logger.error("template_message_timeout", to=to, timeout=30.0)
            return TwilioMessage(
                sid="",
                status="failed",
                error_code="TIMEOUT",
                error_message="Request timed out after 30 seconds"
            )
        except Exception as e:
            logger.error("template_message_exception", to=to, error=str(e))
            return TwilioMessage(
                sid="",
                status="failed",
                error_code="EXCEPTION",
                error_message=str(e)
            )
    
    async def send_text_message(
        self,
        to: str,
        messaging_service_sid: str,
        body: str
    ) -> TwilioMessage:
        """
        Send simple text message via WhatsApp.
        
        Args:
            to: Phone number with whatsapp: prefix
            messaging_service_sid: Twilio Messaging Service SID
            body: Message text content
            
        Returns:
            TwilioMessage with result
        """
        data = {
            "To": to,
            "MessagingServiceSid": messaging_service_sid,
            "Body": body
        }
        
        logger.info("sending_text_message",
            to=to,
            message_length=len(body)
        )
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/Messages.json",
                    headers=self.headers,
                    data=data
                )
                
                response_data = response.json()
                
                if response.status_code == 201:
                    logger.info("text_message_sent_successfully",
                        message_sid=response_data["sid"],
                        status=response_data["status"],
                        to=to
                    )
                    return TwilioMessage(
                        sid=response_data["sid"],
                        status=response_data["status"]
                    )
                else:
                    logger.error("text_message_send_failed",
                        status_code=response.status_code,
                        error_code=response_data.get("code"),
                        error_message=response_data.get("message"),
                        to=to
                    )
                    return TwilioMessage(
                        sid="",
                        status="failed",
                        error_code=str(response_data.get("code", response.status_code)),
                        error_message=response_data.get("message", "Unknown error")
                    )
                    
        except httpx.TimeoutException:
            logger.error("text_message_timeout", to=to, timeout=30.0)
            return TwilioMessage(
                sid="",
                status="failed",
                error_code="TIMEOUT",
                error_message="Request timed out after 30 seconds"
            )
        except Exception as e:
            logger.error("text_message_exception", to=to, error=str(e))
            return TwilioMessage(
                sid="",
                status="failed",
                error_code="EXCEPTION",
                error_message=str(e)
            )
    
    async def send_media_message(
        self,
        to: str,
        messaging_service_sid: str,
        media_url: str,
        body: Optional[str] = None
    ) -> TwilioMessage:
        """
        Send media message (image, document, etc.) via WhatsApp.
        
        Args:
            to: Phone number with whatsapp: prefix
            messaging_service_sid: Twilio Messaging Service SID
            media_url: URL of media to send
            body: Optional caption text
            
        Returns:
            TwilioMessage with result
        """
        data = {
            "To": to,
            "MessagingServiceSid": messaging_service_sid,
            "MediaUrl": media_url
        }
        
        if body:
            data["Body"] = body
        
        logger.info("sending_media_message",
            to=to,
            media_url=media_url,
            has_caption=body is not None
        )
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:  # Longer timeout for media
                response = await client.post(
                    f"{self.base_url}/Messages.json",
                    headers=self.headers,
                    data=data
                )
                
                response_data = response.json()
                
                if response.status_code == 201:
                    logger.info("media_message_sent_successfully",
                        message_sid=response_data["sid"],
                        status=response_data["status"],
                        to=to
                    )
                    return TwilioMessage(
                        sid=response_data["sid"],
                        status=response_data["status"]
                    )
                else:
                    logger.error("media_message_send_failed",
                        status_code=response.status_code,
                        error_code=response_data.get("code"),
                        error_message=response_data.get("message"),
                        to=to
                    )
                    return TwilioMessage(
                        sid="",
                        status="failed",
                        error_code=str(response_data.get("code", response.status_code)),
                        error_message=response_data.get("message", "Unknown error")
                    )
                    
        except httpx.TimeoutException:
            logger.error("media_message_timeout", to=to, timeout=60.0)
            return TwilioMessage(
                sid="",
                status="failed",
                error_code="TIMEOUT",
                error_message="Request timed out after 60 seconds"
            )
        except Exception as e:
            logger.error("media_message_exception", to=to, error=str(e))
            return TwilioMessage(
                sid="",
                status="failed",
                error_code="EXCEPTION",
                error_message=str(e)
            ) 