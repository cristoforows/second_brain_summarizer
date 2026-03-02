from __future__ import annotations

import structlog
from langchain_core.tools import tool

from second_brain.services.drive import DriveService

log = structlog.get_logger()

# Module-level reference set during initialization.
# Tools are closures over this instance.
_drive: DriveService | None = None
_output_folder_id: str = ""


def init_tools(drive: DriveService, output_folder_id: str) -> None:
    """Initialize the module with a DriveService instance and output folder ID.

    Must be called before any tool is invoked.
    """
    global _drive, _output_folder_id
    _drive = drive
    _output_folder_id = output_folder_id


def _get_drive() -> DriveService:
    if _drive is None:
        raise RuntimeError("Drive tools not initialized — call init_tools() first")
    return _drive


def _resolve_category_folder(category_name: str) -> str | None:
    """Find the folder ID for a category by name. Returns None if not found."""
    drive = _get_drive()
    result = drive.find_file(_output_folder_id, category_name)
    if result and result.get("mimeType") == "application/vnd.google-apps.folder":
        return result["id"]
    return None


# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------


@tool
def read_directory_index() -> str:
    """Read the directory.md file from the output folder to understand existing categories and structure.

    Call this first to learn what categories exist and how the knowledge base
    is organized before making any changes. Returns the content of directory.md,
    or a message indicating it doesn't exist yet.
    """
    drive = _get_drive()
    result = drive.find_file(_output_folder_id, "directory.md")
    if result is None:
        return "directory.md does not exist yet. This is a fresh knowledge base."
    return drive.read_file_raw(result["id"])


@tool
def read_category_summary(category_name: str) -> str:
    """Read the summary file for a category to understand what it contains.

    Args:
        category_name: Name of the category folder (e.g., "work", "health").

    Returns the content of the category's summary file ({category_name}.md
    inside the category folder), or a message if the category or summary
    doesn't exist.
    """
    drive = _get_drive()
    folder_id = _resolve_category_folder(category_name)
    if folder_id is None:
        return f"Category '{category_name}' does not exist."
    summary = drive.find_file(folder_id, f"{category_name}.md")
    if summary is None:
        return f"Category '{category_name}' exists but has no summary file yet."
    return drive.read_file_raw(summary["id"])


@tool
def read_file(category_name: str, filename: str) -> str:
    """Read an existing note file from a category folder.

    Always read a file before updating it so you can merge new content with
    existing content rather than overwriting.

    Args:
        category_name: Name of the category folder (e.g., "work").
        filename: Name of the file to read (e.g., "dashboard-redesign.md").
    """
    drive = _get_drive()
    folder_id = _resolve_category_folder(category_name)
    if folder_id is None:
        return f"Category '{category_name}' does not exist."
    file_info = drive.find_file(folder_id, filename)
    if file_info is None:
        return f"File '{filename}' not found in category '{category_name}'."
    return drive.read_file_raw(file_info["id"])


@tool
def write_to_category(category_name: str, filename: str, content: str) -> str:
    """Create or update a note file in a category folder.

    If the file already exists it will be overwritten — so always read the
    file first with ``read_file`` and merge content yourself before calling
    this tool.

    Args:
        category_name: Name of the category folder.
        filename: Descriptive kebab-case filename (e.g., "running-log.md").
        content: Full markdown content to write.
    """
    drive = _get_drive()
    folder_id = _resolve_category_folder(category_name)
    if folder_id is None:
        return (
            f"Category '{category_name}' does not exist. "
            f"Create it first with create_new_category."
        )
    existing = drive.find_file(folder_id, filename)
    if existing:
        drive.update_file(existing["id"], content)
        return f"Updated '{filename}' in category '{category_name}'."
    else:
        drive.write_file(folder_id, filename, content)
        return f"Created '{filename}' in category '{category_name}'."


@tool
def update_category_summary(category_name: str, summary: str) -> str:
    """Update (or create) the summary file for a category.

    The summary should contain:
    1. A short (2-4 sentence) overview of what the category contains.
    2. A "Files" directory listing every file in the category with a
       one-line description of its contents.

    This is regenerated each run after all new messages have been placed.

    Args:
        category_name: Name of the category folder.
        summary: Full markdown summary including overview and file directory.
    """
    drive = _get_drive()
    folder_id = _resolve_category_folder(category_name)
    if folder_id is None:
        return (
            f"Category '{category_name}' does not exist. "
            f"Create it first with create_new_category."
        )
    summary_name = f"{category_name}.md"
    existing = drive.find_file(folder_id, summary_name)
    if existing:
        drive.update_file(existing["id"], summary)
        return f"Updated summary for category '{category_name}'."
    else:
        drive.write_file(folder_id, summary_name, summary)
        return f"Created summary for category '{category_name}'."


@tool
def update_directory_index(content: str) -> str:
    """Update the root directory.md that lists all categories and their descriptions.

    Call this after creating new categories or when the structure has changed.

    Args:
        content: Full markdown content for directory.md.
    """
    drive = _get_drive()
    existing = drive.find_file(_output_folder_id, "directory.md")
    if existing:
        drive.update_file(existing["id"], content)
        return "Updated directory.md."
    else:
        drive.write_file(_output_folder_id, "directory.md", content)
        return "Created directory.md."


@tool
def create_new_category(category_name: str, description: str) -> str:
    """Create a new category folder with an initial summary file.

    Use this when no existing category fits a message. After creating the
    category, remember to update directory.md to include it.

    Args:
        category_name: Short lowercase name for the folder (e.g., "finance").
        description: Brief description of what belongs in this category.
    """
    drive = _get_drive()
    # Check if it already exists
    if _resolve_category_folder(category_name) is not None:
        return f"Category '{category_name}' already exists."
    folder_id = drive.create_folder(_output_folder_id, category_name)
    summary_content = f"# {category_name.title()}\n\n{description}\n"
    drive.write_file(folder_id, f"{category_name}.md", summary_content)
    log.info("category_created", category=category_name)
    return f"Created category '{category_name}' with initial summary."


def get_all_tools() -> list:
    """Return all LangChain tools for registration with the agent."""
    return [
        read_directory_index,
        read_category_summary,
        read_file,
        write_to_category,
        update_category_summary,
        update_directory_index,
        create_new_category,
    ]
