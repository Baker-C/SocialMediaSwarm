"""Fernet helpers for encrypting Twitter credentials at rest."""

from cryptography.fernet import Fernet, InvalidToken


def fernet_from_key(key: str | bytes) -> Fernet:
    """Build Fernet from URL-safe base64 32-byte key (same format Fernet.generate_key())."""
    if isinstance(key, str):
        key = key.encode("utf-8")
    return Fernet(key)


def encrypt_value(fernet: Fernet, plaintext: str) -> str:
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(fernet: Fernet, token: str) -> str:
    try:
        return fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted payload or wrong ENCRYPTION_KEY") from exc
