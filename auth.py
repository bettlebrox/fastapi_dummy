import logging
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt.exceptions import InvalidTokenError
import os
from typing import Optional

security = HTTPBearer()


class AuthError(Exception):
    def __init__(self, error: str, status_code: int):
        self.error = error
        self.status_code = status_code


async def validate_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Validate the Azure AD token and return the decoded token data
    """
    try:
        token = credentials.credentials
        # Get the tenant ID and client ID from environment variables
        tenant_id = os.getenv("AZURE_TENANT_ID")
        client_id = os.getenv("AZURE_API_CLIENT_ID")

        # Get the signing keys from Azure AD
        jwks_uri = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        jwks_client = jwt.PyJWKClient(jwks_uri)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        # Decode and validate the token
        decoded_token = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=f"{client_id}",
            issuer=f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        )

        # Verify the token has the required scope
        if "access_as_user" not in decoded_token.get("scp", []):
            raise AuthError("Token does not have required scope", 403)

        return decoded_token
    except InvalidTokenError as e:
        # Log detailed information about token validation failure
        if "Signature verification failed" in str(e):
            logging.error(
                f"Token signature verification failed. Error details: {str(e)}"
            )
            logging.error(
                f"Token: {token[:20]}... (truncated)"
            )  # Log part of token safely
        raise AuthError(f"Invalid token: {str(e)}", 401)
    except Exception as e:
        raise AuthError(f"Authentication error: {str(e)}", 401)


def get_current_user(token_data: dict = Depends(validate_token)) -> dict:
    """
    Get the current user from the validated token
    """
    return {
        "id": token_data.get("oid"),
        "name": token_data.get("name"),
        "email": token_data.get("preferred_username"),
    }
