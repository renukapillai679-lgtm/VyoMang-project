"""Passwords, app JWT tokens, and Google ID-token verification."""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from fastapi import HTTPException
from google.auth.exceptions import TransportError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

GOOGLE_CLIENT_ID = os.getenv(
    "GOOGLE_CLIENT_ID", "521747064551-mksk1rnspf6lh90tj6up95mil7garnuu.apps.googleusercontent.com")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "12"))


def _load_jwt_secret() -> str:
    """Use the JWT_SECRET environment variable if set; otherwise create one and remember it in .jwt_secret."""
    if os.getenv("JWT_SECRET"):
        return os.environ["JWT_SECRET"]
    path = Path(__file__).resolve().parent / ".jwt_secret"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
    return path.read_text().strip()


JWT_SECRET = _load_jwt_secret()


# ---- passwords ---------------------------------------------------------------
def hash_password(password: str, salt: Optional[str] = None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return salt, digest.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    if not salt or not expected_hash:          # Google-only accounts have no password
        return False
    return secrets.compare_digest(hash_password(password, salt)[1], expected_hash)


# ---- app tokens (JWT) ------------------------------------------------------------
def create_access_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "email": email, "iat": now,
               "exp": now + timedelta(hours=JWT_EXPIRE_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Raises jwt.ExpiredSignatureError / jwt.PyJWTError when the token is expired or tampered with."""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ---- Google ----------------------------------------------------------------------
class _FastRequest(google_requests.Request):
    """Same as google's Request, but gives up after 8 seconds instead of 120 if Google is unreachable."""

    def __call__(self, url, method="GET", body=None, headers=None, timeout=8, **kwargs):
        return super().__call__(url, method, body, headers, timeout=timeout, **kwargs)


def verify_google_credential(credential: str) -> dict:
    """Check the ID token Google gave the browser. Returns its payload (email, name, sub, picture ...)."""
    try:
        info = id_token.verify_oauth2_token(
            credential, _FastRequest(), GOOGLE_CLIENT_ID, clock_skew_in_seconds=10)
    except ValueError:
        raise HTTPException(401, "Invalid or expired Google sign-in. Please try again.")
    except TransportError:
        raise HTTPException(503, "Could not reach Google to verify your sign-in. Check your internet connection.")
    if not info.get("email") or not info.get("email_verified"):
        raise HTTPException(401, "Your Google email address is not verified.")
    return info
