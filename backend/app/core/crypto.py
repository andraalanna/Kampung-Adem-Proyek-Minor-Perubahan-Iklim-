"""Phone number protection: AES-GCM encryption + keyed hash for lookup + masking for UI."""

import base64
import hashlib
import hmac
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_LEN = 12


def _key(b64: str) -> bytes:
    key = base64.b64decode(b64)
    if len(key) != 32:
        raise ValueError("PHONE_ENC_KEY must be 32 bytes, base64-encoded")
    return key


def normalize_phone(raw: str) -> str:
    """Normalize Indonesian numbers to E.164 digits without '+', e.g. 6281234567890."""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    if not re.fullmatch(r"62\d{8,13}", digits):
        raise ValueError("nomor HP tidak valid")
    return digits


def encrypt_phone(phone: str, key_b64: str) -> str:
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(_key(key_b64)).encrypt(nonce, phone.encode(), b"phone")
    return base64.b64encode(nonce + ct).decode()


def decrypt_phone(token: str, key_b64: str) -> str:
    raw = base64.b64decode(token)
    return AESGCM(_key(key_b64)).decrypt(raw[:_NONCE_LEN], raw[_NONCE_LEN:], b"phone").decode()


def hash_phone(phone: str, hash_key_b64: str) -> str:
    """Keyed hash (HMAC-SHA256): phone numbers are low-entropy, so a plain hash is guessable."""
    return hmac.new(base64.b64decode(hash_key_b64), phone.encode(), hashlib.sha256).hexdigest()


def mask_phone(phone: str) -> str:
    """6281234567890 -> 0812xxxx890"""
    local = "0" + phone[2:] if phone.startswith("62") else phone
    if len(local) < 8:
        return "x" * len(local)
    return local[:4] + "x" * (len(local) - 7) + local[-3:]
