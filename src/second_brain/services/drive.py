from __future__ import annotations

import io
from typing import Any

import structlog
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

from second_brain.services.auth import load_credentials

log = structlog.get_logger()


def _escape_drive_query(value: str) -> str:
    """Escape a value for safe interpolation into a Drive API query string."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


class DriveService:
    """Google Drive CRUD operations via OAuth2 user credentials.

    This is a raw API wrapper with no LangChain awareness.
    """

    def __init__(self, token_path: str) -> None:
        creds = load_credentials(token_path)
        self._service = build("drive", "v3", credentials=creds)
        log.info("drive_service_initialized", token_path=token_path)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def list_files(
        self, folder_id: str, mime_type: str | None = None
    ) -> list[dict[str, Any]]:
        """List files in a folder. Optionally filter by MIME type."""
        query = f"parents='{_escape_drive_query(folder_id)}' and trashed = false"
        if mime_type:
            query += f" and mimeType = '{_escape_drive_query(mime_type)}'"

        results: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            try:
                resp = (
                    self._service.files()
                    .list(
                        q=query,
                        fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
                        pageToken=page_token,
                    )
                    .execute()
                )
            except HttpError as e:
                log.error("drive_list_files_failed", folder_id=folder_id, status=e.status_code, error=str(e))
                raise
            results.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return results

    def read_file(self, file_id: str) -> str:
        """Download and return the text content of a file."""
        try:
            content = (
                self._service.files()
                .export(fileId=file_id, mimeType="text/plain")
                .execute()
            )
        except HttpError as e:
            log.error("drive_read_file_failed", file_id=file_id, status=e.status_code, error=str(e))
            raise
        try:
            return content.decode("utf-8") if isinstance(content, bytes) else str(content)
        except UnicodeDecodeError as e:
            log.error("drive_read_file_decode_failed", file_id=file_id, error=str(e))
            raise

    def read_file_raw(self, file_id: str) -> str:
        """Download raw file content (for non-Google-Docs files like .md)."""
        try:
            content = self._service.files().get_media(fileId=file_id).execute()
        except HttpError as e:
            log.error("drive_read_file_raw_failed", file_id=file_id, status=e.status_code, error=str(e))
            raise
        try:
            return content.decode("utf-8") if isinstance(content, bytes) else str(content)
        except UnicodeDecodeError as e:
            log.error("drive_read_file_raw_decode_failed", file_id=file_id, error=str(e))
            raise

    def find_file(self, folder_id: str, name: str) -> dict[str, Any] | None:
        """Find a file by exact name within a folder. Returns None if not found."""
        query = (
            f"parents='{_escape_drive_query(folder_id)}' "
            f"and name = '{_escape_drive_query(name)}' "
            f"and trashed = false"
        )
        try:
            resp = (
                self._service.files()
                .list(q=query, fields="files(id, name, mimeType)", pageSize=1)
                .execute()
            )
        except HttpError as e:
            log.error("drive_find_file_failed", folder_id=folder_id, name=name, status=e.status_code, error=str(e))
            raise
        files = resp.get("files", [])
        return files[0] if files else None

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
        try:
            created = (
                self._service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )
        except HttpError as e:
            log.error("drive_write_file_failed", name=name, folder_id=folder_id, status=e.status_code, error=str(e))
            raise
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
        try:
            self._service.files().update(fileId=file_id, media_body=media).execute()
        except HttpError as e:
            log.error("drive_update_file_failed", file_id=file_id, status=e.status_code, error=str(e))
            raise
        log.info("file_updated", file_id=file_id)

    def create_folder(self, parent_id: str, name: str) -> str:
        """Create a subfolder. Returns the new folder ID."""
        file_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        try:
            folder = (
                self._service.files()
                .create(body=file_metadata, fields="id")
                .execute()
            )
        except HttpError as e:
            log.error("drive_create_folder_failed", name=name, parent_id=parent_id, status=e.status_code, error=str(e))
            raise
        folder_id = folder["id"]
        log.info("folder_created", name=name, parent_id=parent_id, folder_id=folder_id)
        return folder_id
