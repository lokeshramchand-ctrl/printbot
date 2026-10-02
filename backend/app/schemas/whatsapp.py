from pydantic import BaseModel
from typing import Optional, List, Any, Dict

class WebhookVerificationQuery(BaseModel):
    hub_mode: str
    hub_challenge: str
    hub_verify_token: str

class WhatsAppWebhookPayload(BaseModel):
    object: Optional[str] = None
    entry: Optional[List[Dict[str, Any]]] = None
