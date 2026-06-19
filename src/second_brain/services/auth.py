from __future__ import annotations

import json
import os

import structlog
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

log = structlog.get_logger()

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar",
]
_CLIENT_SECRETS_FILE = "client_secret.json"


def _write_token(token_path: str, creds: Credentials) -> None:
    """Write OAuth credentials to token_path with owner-only permissions (0o600)."""
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())


def load_credentials(token_path: str) -> Credentials:
    """Load OAuth2 credentials.

    Checks GOOGLE_TOKEN_JSON env var first (used in CI/GHA — no file needed).
    Falls back to token_path on disk (used locally).
    If neither exists, runs the interactive OAuth consent flow.
    """
    token_json_env = os.environ.get("GOOGLE_TOKEN_JSON")

    if token_json_env:
        log.info("loading_credentials_from_env")
        creds = Credentials.from_authorized_user_info(json.loads(token_json_env), scopes=SCOPES)
        from_env = True
    else:
        from_env = False
        token_exists = os.path.isfile(token_path) and os.path.getsize(token_path) > 0
        if token_exists:
            creds = Credentials.from_authorized_user_file(token_path, scopes=SCOPES)
        else:
            log.info("token_missing_starting_oauth_flow", token_path=token_path)
            if not os.path.isfile(_CLIENT_SECRETS_FILE):
                raise FileNotFoundError(
                    f"'{token_path}' is missing or empty and no '{_CLIENT_SECRETS_FILE}' was found.\n"
                    f"Download your OAuth 2.0 client credentials from Google Cloud Console → "
                    f"APIs & Services → Credentials → Download JSON, and save it as '{_CLIENT_SECRETS_FILE}'."
                )
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file(_CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            _write_token(token_path, creds)
            log.info("token_saved", token_path=token_path)

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            if not from_env:
                _write_token(token_path, creds)
        except RefreshError as e:
            log.warning("token_refresh_failed", error=str(e))
            if not from_env:
                os.remove(token_path)
            raise RuntimeError(
                "OAuth token refresh failed. "
                "Re-authenticate by running the script interactively or updating the GOOGLE_TOKEN_JSON secret."
            ) from e

    return creds
