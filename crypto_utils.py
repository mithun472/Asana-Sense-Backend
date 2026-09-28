"""
AES-256-GCM field-level encryption for sensitive user profile data.

Encrypts individual fields (name, bmi_data) before they are written to
MongoDB, and decrypts them when read back out. Email and password are
NOT encrypted here — email must stay queryable for login, and the
password is already one-way hashed via bcrypt (auth.py).

Key setup:
    Generate a 256-bit (32 byte) key once and store it in .env as
    PROFILE_ENCRYPTION_KEY (urlsafe-base64 text):

        python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

    Put the printed value in .env:
        PROFILE_ENCRYPTION_KEY=<the printed value>

    Never commit the real key. Rotating it will make previously
    encrypted fields undecryptable, so back up the key securely.
"""
import os
import json
import base64
from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

load_dotenv()

_NONCE_LEN = 12  # 96-bit nonce, standard for AES-GCM


def _load_key() -> bytes:
    raw = os.getenv("PROFILE_ENCRYPTION_KEY", "")
    if not raw:
        raise RuntimeError(
            "PROFILE_ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())\" "
            "and add it to .env"
        )
    key = base64.urlsafe_b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("PROFILE_ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256).")
    return key


_aesgcm = AESGCM(_load_key())


def encrypt_str(plaintext: str) -> str:
    """Encrypt a plain string. Returns base64(nonce || ciphertext)."""
    if plaintext is None or plaintext == "":
        return plaintext
    nonce = os.urandom(_NONCE_LEN)
    ct = _aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ct).decode("utf-8")


def decrypt_str(token) -> str:
    """
    Decrypt a value produced by encrypt_str.
    Backward-compatible: if token is not a valid encrypted blob
    (e.g. legacy plaintext data written before encryption existed),
    it is returned unchanged instead of raising.
    """
    if token is None or token == "":
        return token
    if not isinstance(token, str):
        return token
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8"))
        nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
        return _aesgcm.decrypt(nonce, ct, None).decode("utf-8")
    except Exception:
        # Legacy unencrypted value already stored in DB — pass through.
        return token


def encrypt_bmi(data) -> str:
    """Encrypt a bmi_data dict as a single JSON blob."""
    if data is None:
        return None
    if not isinstance(data, dict):
        data = data.model_dump() if hasattr(data, "model_dump") else dict(data)
    return encrypt_str(json.dumps(data))


def decrypt_bmi(token):
    """Decrypt a bmi_data blob back into a dict. Backward-compatible with legacy plain dicts."""
    if token is None:
        return None
    if isinstance(token, dict):
        # Legacy unencrypted document already stored in DB.
        return token
    decrypted = decrypt_str(token)
    try:
        return json.loads(decrypted)
    except (TypeError, json.JSONDecodeError):
        return None
