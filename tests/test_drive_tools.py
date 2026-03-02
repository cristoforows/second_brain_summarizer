from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from second_brain.tools import drive_tools
from second_brain.tools.drive_tools import (
    create_new_category,
    init_tools,
    read_category_summary,
    read_directory_index,
    read_file,
    update_category_summary,
    update_directory_index,
    write_to_category,
)


@pytest.fixture(autouse=True)
def _setup_drive_tools() -> None:
    """Inject a mock DriveService into the tools module for every test."""
    mock_drive = MagicMock()
    init_tools(mock_drive, "output-root")
    yield
    # Reset after test
    drive_tools._drive = None
    drive_tools._output_folder_id = ""


def _drive() -> MagicMock:
    return drive_tools._drive  # type: ignore[return-value]


# ------------------------------------------------------------------
# read_directory_index
# ------------------------------------------------------------------

class TestReadDirectoryIndex:
    def test_fresh_knowledge_base(self) -> None:
        _drive().find_file.return_value = None
        result = read_directory_index.invoke({})
        assert "does not exist yet" in result

    def test_existing_directory(self) -> None:
        _drive().find_file.return_value = {"id": "dir-id"}
        _drive().read_file_raw.return_value = "# Directory\n- work\n- health"
        result = read_directory_index.invoke({})
        assert "# Directory" in result


# ------------------------------------------------------------------
# read_category_summary
# ------------------------------------------------------------------

class TestReadCategorySummary:
    def test_category_not_found(self) -> None:
        _drive().find_file.return_value = None
        result = read_category_summary.invoke({"category_name": "nope"})
        assert "does not exist" in result

    def test_summary_found(self) -> None:
        _drive().find_file.side_effect = [
            {"id": "folder-id", "mimeType": "application/vnd.google-apps.folder"},
            {"id": "summary-id"},
        ]
        _drive().read_file_raw.return_value = "# Work\nSummary here."
        result = read_category_summary.invoke({"category_name": "work"})
        assert "# Work" in result


# ------------------------------------------------------------------
# read_file
# ------------------------------------------------------------------

class TestReadFile:
    def test_category_not_found(self) -> None:
        _drive().find_file.return_value = None
        result = read_file.invoke({"category_name": "nope", "filename": "x.md"})
        assert "does not exist" in result

    def test_file_not_found(self) -> None:
        _drive().find_file.side_effect = [
            {"id": "folder-id", "mimeType": "application/vnd.google-apps.folder"},
            None,
        ]
        result = read_file.invoke({"category_name": "work", "filename": "x.md"})
        assert "not found" in result

    def test_file_found(self) -> None:
        _drive().find_file.side_effect = [
            {"id": "folder-id", "mimeType": "application/vnd.google-apps.folder"},
            {"id": "file-id"},
        ]
        _drive().read_file_raw.return_value = "File content here."
        result = read_file.invoke({"category_name": "work", "filename": "notes.md"})
        assert result == "File content here."


# ------------------------------------------------------------------
# write_to_category
# ------------------------------------------------------------------

class TestWriteToCategory:
    def test_category_missing(self) -> None:
        _drive().find_file.return_value = None
        result = write_to_category.invoke(
            {"category_name": "nope", "filename": "x.md", "content": "hi"}
        )
        assert "does not exist" in result

    def test_creates_new_file(self) -> None:
        _drive().find_file.side_effect = [
            {"id": "folder-id", "mimeType": "application/vnd.google-apps.folder"},
            None,  # file doesn't exist yet
        ]
        _drive().write_file.return_value = "new-file-id"
        result = write_to_category.invoke(
            {"category_name": "work", "filename": "new.md", "content": "content"}
        )
        assert "Created" in result
        _drive().write_file.assert_called_once()

    def test_updates_existing_file(self) -> None:
        _drive().find_file.side_effect = [
            {"id": "folder-id", "mimeType": "application/vnd.google-apps.folder"},
            {"id": "existing-id"},
        ]
        result = write_to_category.invoke(
            {"category_name": "work", "filename": "old.md", "content": "updated"}
        )
        assert "Updated" in result
        _drive().update_file.assert_called_once_with("existing-id", "updated")


# ------------------------------------------------------------------
# update_category_summary
# ------------------------------------------------------------------

class TestUpdateCategorySummary:
    def test_category_missing(self) -> None:
        _drive().find_file.return_value = None
        result = update_category_summary.invoke(
            {"category_name": "nope", "summary": "x"}
        )
        assert "does not exist" in result

    def test_creates_summary(self) -> None:
        _drive().find_file.side_effect = [
            {"id": "folder-id", "mimeType": "application/vnd.google-apps.folder"},
            None,
        ]
        _drive().write_file.return_value = "new-id"
        result = update_category_summary.invoke(
            {"category_name": "work", "summary": "# Work\nOverview."}
        )
        assert "Created summary" in result

    def test_updates_summary(self) -> None:
        _drive().find_file.side_effect = [
            {"id": "folder-id", "mimeType": "application/vnd.google-apps.folder"},
            {"id": "summary-id"},
        ]
        result = update_category_summary.invoke(
            {"category_name": "work", "summary": "updated"}
        )
        assert "Updated summary" in result
        _drive().update_file.assert_called_once_with("summary-id", "updated")


# ------------------------------------------------------------------
# update_directory_index
# ------------------------------------------------------------------

class TestUpdateDirectoryIndex:
    def test_creates_directory(self) -> None:
        _drive().find_file.return_value = None
        _drive().write_file.return_value = "new-id"
        result = update_directory_index.invoke({"content": "# Dir"})
        assert "Created" in result

    def test_updates_directory(self) -> None:
        _drive().find_file.return_value = {"id": "dir-id"}
        result = update_directory_index.invoke({"content": "# Dir updated"})
        assert "Updated" in result
        _drive().update_file.assert_called_once_with("dir-id", "# Dir updated")


# ------------------------------------------------------------------
# create_new_category
# ------------------------------------------------------------------

class TestCreateNewCategory:
    def test_already_exists(self) -> None:
        _drive().find_file.return_value = {
            "id": "folder-id",
            "mimeType": "application/vnd.google-apps.folder",
        }
        result = create_new_category.invoke(
            {"category_name": "work", "description": "Work stuff"}
        )
        assert "already exists" in result

    def test_creates_folder_and_summary(self) -> None:
        _drive().find_file.return_value = None
        _drive().create_folder.return_value = "new-folder-id"
        _drive().write_file.return_value = "summary-id"
        result = create_new_category.invoke(
            {"category_name": "finance", "description": "Money matters"}
        )
        assert "Created category" in result
        _drive().create_folder.assert_called_once_with("output-root", "finance")
        _drive().write_file.assert_called_once()
