"""WhatsApp Cloud API (Meta) client. Official Graph API only, approved utility templates only."""

import hashlib
import hmac

import httpx

from app.config import Settings

TEMPLATE_ALERT = "peringatan_panas_rw"
TEMPLATE_DOWN = "status_panas_turun"
ALERT_TEMPLATES = (TEMPLATE_ALERT, TEMPLATE_DOWN)


class WhatsAppError(Exception):
    def __init__(self, message: str, code: str, retryable: bool):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def send_template(s: Settings, to: str, template: str, params: list[str],
                  client: httpx.Client | None = None) -> str:
    """Send an approved template. Returns the wamid. Raises WhatsAppError."""
    url = f"https://graph.facebook.com/{s.wa_graph_version}/{s.wa_phone_number_id}/messages"
    body = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": s.wa_template_lang},
            "components": [{
                "type": "body",
                "parameters": [{"type": "text", "text": p} for p in params],
            }],
        },
    }
    c = client or httpx.Client(timeout=15)
    try:
        r = c.post(url, json=body, headers={"Authorization": f"Bearer {s.wa_token}"})
    except httpx.HTTPError as exc:
        raise WhatsAppError(str(exc), "network", retryable=True) from exc
    finally:
        if client is None:
            c.close()
    if r.status_code == 200:
        return r.json()["messages"][0]["id"]
    try:
        err = r.json().get("error", {})
    except ValueError:
        err = {}
    code = str(err.get("code", r.status_code))
    retryable = r.status_code == 429 or r.status_code >= 500
    raise WhatsAppError(err.get("message", r.text[:200]), code, retryable)


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """Verify Meta's X-Hub-Signature-256 header ("sha256=<hex>")."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))
