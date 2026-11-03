import base64
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.core.payload import encode_v1
from app.ingest.chirpstack import parse_uplink_event
from app.worker.whatsapp import WhatsAppError, send_template, verify_signature


def test_chirpstack_event_parsing():
    data = encode_v1(7, 33.1, 70.0, 33.0, 70.2, 3.95)
    event = {
        "time": "2026-11-02T06:40:02.123Z",
        "deviceInfo": {"devEui": "70b3d57ed0051234", "deviceName": "KA-SBY-0012"},
        "fCnt": 2291,
        "data": base64.b64encode(data).decode(),
        "rxInfo": [{"gatewayId": "a840411f00000001", "rssi": -104, "snr": -6.5}],
    }
    up = parse_uplink_event(event)
    assert up.dev_eui == "70b3d57ed0051234" and up.payload == data and up.f_cnt == 2291
    assert up.received_at.utcoffset().total_seconds() == 0
    assert up.gateways[0].rssi == -104


def test_meta_signature():
    body = b'{"entry": []}'
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_signature("secret", body, sig)
    assert not verify_signature("secret", body + b" ", sig)
    assert not verify_signature("secret", body, None)
    assert not verify_signature("", body, sig)


def _settings():
    return Settings(wa_phone_number_id="123", wa_token="tok", wa_graph_version="v23.0")


def test_whatsapp_send_success_and_request_shape():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.X"}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        wamid = send_template(_settings(), "6281234567890", "peringatan_panas_rw",
                              ["SIAGA", "RW 03"], client=c)
    assert wamid == "wamid.X"
    assert seen["url"] == "https://graph.facebook.com/v23.0/123/messages"
    assert seen["auth"] == "Bearer tok"
    t = seen["body"]["template"]
    assert t["name"] == "peringatan_panas_rw" and t["language"]["code"] == "id"
    assert [p["text"] for p in t["components"][0]["parameters"]] == ["SIAGA", "RW 03"]


@pytest.mark.parametrize("code,retryable", [(500, True), (429, True), (400, False)])
def test_whatsapp_errors(code, retryable):
    transport = httpx.MockTransport(
        lambda r: httpx.Response(code, json={"error": {"code": 131026, "message": "x"}}))
    with httpx.Client(transport=transport) as c, pytest.raises(WhatsAppError) as ei:
        send_template(_settings(), "62812", "t", [], client=c)
    assert ei.value.retryable is retryable


def test_api_app_imports_and_routes():
    from app.main import app

    paths = set(app.openapi()["paths"])
    for p in ["/api/v1/sensors", "/api/v1/sensors/{sensor_id}/readings", "/api/v1/sensors/readings",
              "/api/v1/heatmap", "/api/v1/regions", "/api/v1/alerts", "/api/v1/dashboard/summary",
              "/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/recipients",
              "/api/v1/thresholds", "/api/v1/maintenance-logs", "/api/v1/webhooks/whatsapp",
              "/api/v1/reports/monthly"]:
        assert p in paths, p


def test_landsat_scaling():
    path = Path(__file__).resolve().parents[2] / "satellite" / "lst_landsat.py"
    spec = importlib.util.spec_from_file_location("lst_landsat", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # DN 44000 -> 44000*0.00341802 + 149 = 299.39 K = 26.24 C
    assert mod.st_dn_to_celsius(44000) == pytest.approx(26.24, abs=0.01)
