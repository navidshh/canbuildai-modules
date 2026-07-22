# auth/cognito.py
import logging
import requests
from jose import jwt, jwk
from jose.utils import base64url_decode
from fastapi import HTTPException, status

from ..api_config import settings


logger = logging.getLogger(__name__)


# Store JWKS keys globally to avoid fetching them on every request
# Handle case where Cognito is not configured (e.g., local dev or auth disabled)
try:
    logger.info("Fetching Cognito JWKS from %s", settings.JWKS_URL)
    response = requests.get(settings.JWKS_URL, timeout=5)
    response.raise_for_status()
    jwks = response.json()["keys"]
    logger.info("Loaded %d Cognito JWKS keys", len(jwks))
except Exception as e:
    logger.exception("Could not fetch Cognito JWKS keys from %s: %s", settings.JWKS_URL, e)
    jwks = []


def get_cognito_login_url():
    """Constructs the Cognito Hosted UI login URL."""
    return (
        f"{settings.COGNITO_DOMAIN}/login?response_type=code&client_id={settings.COGNITO_APP_CLIENT_ID}"
        f"&redirect_uri={settings.REDIRECT_URI}&scope=email+openid+profile"
    )

def validate_token(token: str):
    """Validates a JWT token from Cognito."""
    if not jwks:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Auth misconfigured: no Cognito JWKS keys loaded "
                f"(check COGNITO_REGION / COGNITO_USER_POOL_ID; JWKS_URL={settings.JWKS_URL})"
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        # 1. Get the key ID (kid) from the token header
        header = jwt.get_unverified_header(token)
        kid = header["kid"]

        # 2. Find the corresponding key in the JWKS
        key = next((k for k in jwks if k["kid"] == kid), None)
        if not key:
            raise HTTPException(status_code=401, detail=f"Public key for kid={kid!r} not found in JWKS (issuer expected: {settings.COGNITO_ISSUER})")

        # 3. Decode and verify the token's signature
        public_key = jwk.construct(key)
        message, encoded_signature = str(token).rsplit(".", 1)
        decoded_signature = base64url_decode(encoded_signature.encode("utf-8"))
        
        if not public_key.verify(message.encode("utf-8"), decoded_signature):
            raise HTTPException(status_code=401, detail="Signature verification failed")
            
        # 4. Verify claims
        claims = jwt.get_unverified_claims(token)
        if claims["iss"] != settings.COGNITO_ISSUER:
            raise HTTPException(status_code=401, detail=f"Invalid issuer (token iss={claims.get('iss')!r}, expected {settings.COGNITO_ISSUER!r})")
        if claims["token_use"] not in ["id", "access"]:
             raise HTTPException(status_code=401, detail=f"Invalid token_use={claims.get('token_use')!r}")

        # Note: The `exp` claim (expiration time) is automatically checked by some libraries,
        # but it's good practice to be aware of it.
        
        return claims

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {type(e).__name__}: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
