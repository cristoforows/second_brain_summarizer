from __future__ import annotations

import io
import os
from typing import Any

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

log = structlog.get_logger()

_SCOPES = ["https://www.googleapis.com/auth/drive"]
_CLIENT_SECRETS_FILE = "client_secret.json"


def _load_credentials(token_path: str) -> Credentials:
    """Load OAuth2 credentials from token_path.

    If the file is missing or empty, run the local OAuth consent flow using
    client_secret.json to obtain a fresh token, then save it to token_path.
    """
    token_exists = os.path.isfile(token_path) and os.path.getsize(token_path) > 0

    if token_exists:
        creds = Credentials.from_authorized_user_file(token_path, scopes=_SCOPES)
    else:
        log.info("token_missing_starting_oauth_flow", token_path=token_path)
        if not os.path.isfile(_CLIENT_SECRETS_FILE):
            raise FileNotFoundError(
                f"'{token_path}' is missing or empty and no '{_CLIENT_SECRETS_FILE}' was found.\n"
                f"Download your OAuth 2.0 client credentials from Google Cloud Console → "
                f"APIs & Services → Credentials → Download JSON, and save it as '{_CLIENT_SECRETS_FILE}'."
            )
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(_CLIENT_SECRETS_FILE, _SCOPES)
        creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        log.info("token_saved", token_path=token_path)

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            log.warning("token_refresh_failed_restarting_oauth_flow", token_path=token_path)
            os.remove(token_path)
            return _load_credentials(token_path)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return creds


class DriveService:
    """Google Drive CRUD operations via OAuth2 user credentials.

    This is a raw API wrapper with no LangChain awareness.
    """

    def __init__(self, token_path: str) -> None:
        creds = _load_credentials(token_path)
        self._service = build("drive", "v3", credentials=creds)
        log.info("drive_service_initialized", token_path=token_path)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_files(
        self, folder_id: str, mime_type: str | None = None
    ) -> list[dict[str, Any]]:
        """List files in a folder. Optionally filter by MIME type."""
        query = f"parents='{folder_id}' and trashed = false"
        if mime_type:
            query += f" and mimeType = '{mime_type}'"

        results: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            resp = (
                self._service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                    pageToken=page_token,
                )
                .execute()
            )
            results.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return results

    def read_file(self, file_id: str) -> str:
        """Download and return the text content of a file."""
        content = (
            self._service.files()
            .export(fileId=file_id, mimeType="text/plain")
            .execute()
        )
        if isinstance(content, bytes):
            return content.decode("utf-8")
        return str(content)

    def read_file_raw(self, file_id: str) -> str:
        """Download raw file content (for non-Google-Docs files like .md)."""
        content = self._service.files().get_media(fileId=file_id).execute()
        if isinstance(content, bytes):
            return content.decode("utf-8")
        return str(content)

    def find_file(self, folder_id: str, name: str) -> dict[str, Any] | None:
        """Find a file by exact name within a folder. Returns None if not found."""
        query = (
            f"parents='{folder_id}' "
            f"and name = '{name}' "
            f"and trashed = false"
        )
        resp = (
            self._service.files()
            .list(q=query, fields="files(id, name, mimeType)", pageSize=1)
            .execute()
        )
        files = resp.get("files", [])
        return files[0] if files else None

    def find_folder(self, folder_id: str) -> dict[str, Any] | None:
        """Find a folder by exact id. Returns None if not found."""
        try:
            results = self._service.files().list(
                q="name='second_brain_bot' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                spaces='drive',
                fields='files(id, name)',
            ).execute()
            folders = results.get('files', [])
            if folders:
                folder_id = folders[0]['id']
                log.info(f"Found existing folder: second_brain_bot (ID: {folder_id})")
                return folder_id
        except Exception as e:
            log.error("Failed to get folder", error=e)
            return None


    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def write_file(self, folder_id: str, name: str, content: str) -> str:
        """Create a new file in the given folder. Returns the new file ID."""
        file_metadata = {
            "name": name,
            "parents": [folder_id],
        }
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")),
            mimetype="text/markdown",
            resumable=False,
        )
        created = (
            self._service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )
        file_id = created["id"]
        log.info("file_created", name=name, folder_id=folder_id, file_id=file_id)
        return file_id

    def update_file(self, file_id: str, content: str) -> None:
        """Overwrite the content of an existing file."""
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")),
            mimetype="text/markdown",
            resumable=False,
        )
        self._service.files().update(fileId=file_id, media_body=media).execute()
        log.info("file_updated", file_id=file_id)

    def create_folder(self, parent_id: str, name: str) -> str:
        """Create a subfolder. Returns the new folder ID."""
        file_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = (
            self._service.files()
            .create(body=file_metadata, fields="id")
            .execute()
        )
        folder_id = folder["id"]
        log.info("folder_created", name=name, parent_id=parent_id, folder_id=folder_id)
        return folder_id
