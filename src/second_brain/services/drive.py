from __future__ import annotations

import io
from typing import Any

import structlog
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

log = structlog.get_logger()

_SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveService:
    """Google Drive CRUD operations via a service account.

    This is a raw API wrapper with no LangChain awareness.
    """

    def __init__(self, refresh_token: str) -> None:
        creds = Credentials.from_authorized_user_file(refresh_token, scopes=_SCOPES)
    
    # If the access token is expired, refresh it silently
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Update the file so we don't have to refresh again for another hour
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
                
        self._service = build('drive', 'v3', credentials=creds)
        log.info("drive_service_initialized", refresh_token=refresh_token)

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
            print(resp)
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
        log.warning("files", files=files)
        return files[0] if files else None

    def find_folder(self, folder_id: str) -> dict[str, Any] | None:
        """Find a folder by exact id. Returns None if not found."""
        try:
            results = self._service.files().list(
                q=f"name='{"second_brain_bot"}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
                spaces='drive',
                fields='files(id, name)',
            ).execute()
            folders = results.get('files', [])
            if folders:
                folder_id = folders[0]['id']
                log.info(f"Found existing folder: {"second_brain_bot"} (ID: {folder_id})")
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
