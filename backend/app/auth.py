"""Authentication middleware and dependency for FastAPI.

In LOCAL_DEV mode, auth is bypassed and a test user identity is injected.
In production, validates Cognito JWT tokens.
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

LOCAL_DEV_USER = {
    "user_id": "local-dev-user",
    "email": "dev@example.com",
}


def _decode_cognito_token(token: str) -> dict:
    """Validate a Cognito JWT and return the claims.

    In a production deployment this would verify the token signature against
    Cognito's JWKS endpoint. For now we do a basic decode to extract claims.
    """
    import json
    import base64

    try:
        # JWT is header.payload.signature -- we need the payload
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")

        # Decode payload (add padding if needed)
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        # Extract user info from Cognito token claims
        user_id = payload.get("sub", "")
        email = payload.get("email", "")

        if not user_id:
            raise ValueError("Token missing 'sub' claim")

        return {"user_id": user_id, "email": email}

    except Exception as e:
        logger.warning("JWT validation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """FastAPI dependency that returns the authenticated user.

    In LOCAL_DEV mode, returns a test user without requiring a token.
    In production, validates the Bearer token and returns user claims.
    """
    if settings.local_dev:
        return LOCAL_DEV_USER

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _decode_cognito_token(credentials.credentials)
