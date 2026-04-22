from __future__ import annotations

import structlog
from langchain_core.tools import tool

from second_brain.services.drive import DriveService

log = structlog.get_logger()

# Module-level reference set during initialization.
# Tools are closures over this instance.
_drive: DriveService | None = None
_output_folder_id: str = ""
_dry_run: bool = False


def init_tools(drive: DriveService, output_folder_id: str, dry_run: bool = False) -> None:
    """Initialize the module with a DriveService instance and output folder ID.

    Must be called before any tool is invoked.
    """
    global _drive, _output_folder_id, _dry_run
    _drive = drive
    _output_folder_id = output_folder_id
    _dry_run = dry_run


def _get_drive() -> DriveService:
    if _drive is None:
        raise RuntimeError("Drive tools not initialized — call init_tools() first")
    return _drive


def _resolve_folder(path: str) -> str:
    """Navigate output_folder_id using a slash-separated path.

    e.g. "projects/dashboard-redesign" → finds projects/ then dashboard-redesign/ inside it.
    Returns the final folder ID.
    Raises ValueError if any segment is not found.
    """
    drive = _get_drive()
    current_id = _output_folder_id
    for segment in path.split("/"):
        result = drive.find_file(current_id, segment)
        if result is None or result.get("mimeType") != "application/vnd.google-apps.folder":
            raise ValueError(f"Folder '{segment}' not found in path '{path}'")
        current_id = result["id"]
    return current_id


# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------


@tool
def read_directory_index() -> str:
    """Read the directory.md file from the output folder to understand existing sections and structure.

    Call this first to learn what sections exist and how the knowledge base
    is organized before making any changes. Returns the content of directory.md,
    or a message indicating it doesn't exist yet.
    """
    drive = _get_drive()
    result = drive.find_file(_output_folder_id, "directory.md")
    if result is None:
        return "directory.md does not exist yet. This is a fresh knowledge base."
    return drive.read_file_raw(result["id"], "directory.md")


@tool
def read_category_summary(category_name: str) -> str:
    """Read the directory.md for a section or topic folder.

    Args:
        category_name: Slash-separated path to the folder (e.g. "projects" or
            "projects/dashboard-redesign").

    Returns the content of directory.md inside the target folder, or a message
    if the folder or file doesn't exist.
    """
    drive = _get_drive()
    try:
        folder_id = _resolve_folder(category_name)
    except ValueError:
        return f"Path '{category_name}' does not exist."
    summary = drive.find_file(folder_id, "directory.md")
    if summary is None:
        return f"'{category_name}' exists but has no directory.md yet."
    return drive.read_file_raw(summary["id"], f"{category_name}/directory.md")


@tool
def read_file(category_name: str, filename: str) -> str:
    """Read an existing note file from a section or topic folder.

    Always read a file before updating it so you can merge new content with
    existing content rather than overwriting.

    Args:
        category_name: Slash-separated path to the folder (e.g. "projects/dashboard-redesign").
        filename: Name of the file to read (e.g., "notes.md").
    """
    drive = _get_drive()
    try:
        folder_id = _resolve_folder(category_name)
    except ValueError:
        return f"Path '{category_name}' does not exist."
    file_info = drive.find_file(folder_id, filename)
    if file_info is None:
        return f"File '{filename}' not found in '{category_name}'."
    return drive.read_file_raw(file_info["id"], f"{category_name}/{filename}")


@tool
def write_to_category(category_name: str, filename: str, content: str) -> str:
    """Create or update a note file in a section or topic folder.

    If the file already exists it will be overwritten — so always read the
    file first with ``read_file`` and merge content yourself before calling
    this tool.

    Args:
        category_name: Slash-separated path to the folder (e.g. "projects/dashboard-redesign").
        filename: Descriptive kebab-case filename (e.g., "running-log.md").
        content: Full markdown content to write.
    """
    drive = _get_drive()
    try:
        folder_id = _resolve_folder(category_name)
    except ValueError:
        return (
            f"Path '{category_name}' does not exist. "
            f"Create it first with create_new_category."
        )
    existing = drive.find_file(folder_id, filename)
    if _dry_run:
        action = "update" if existing else "create"
        log.info("dry_run_skip", action=action, file=filename, category=category_name)
        return f"[dry-run] Would {action} '{filename}' in '{category_name}'."
    if existing:
        drive.update_file(existing["id"], content, f"{category_name}/{filename}")
        return f"Updated '{filename}' in '{category_name}'."
    else:
        drive.write_file(folder_id, filename, content)
        return f"Created '{filename}' in '{category_name}'."


@tool
def update_category_summary(category_name: str, summary: str) -> str:
    """Update (or create) the directory.md for a section or topic folder.

    Call this after writing files or creating topic folders to keep the
    section's directory.md current.

    Args:
        category_name: Slash-separated path to the folder (e.g. "projects").
        summary: Full markdown content for directory.md.
    """
    drive = _get_drive()
    try:
        folder_id = _resolve_folder(category_name)
    except ValueError:
        return (
            f"Path '{category_name}' does not exist. "
            f"Create it first with create_new_category."
        )
    existing = drive.find_file(folder_id, "directory.md")
    if _dry_run:
        action = "update" if existing else "create"
        log.info("dry_run_skip", action=action, file="directory.md", category=category_name)
        return f"[dry-run] Would {action} directory.md for '{category_name}'."
    if existing:
        drive.update_file(existing["id"], summary, f"{category_name}/directory.md")
        return f"Updated directory for '{category_name}'."
    else:
        drive.write_file(folder_id, "directory.md", summary)
        return f"Created directory for '{category_name}'."


@tool
def update_directory_index(content: str) -> str:
    """Update the root directory.md that lists all sections and their descriptions.

    Call this only when the overall section structure changes.

    Args:
        content: Full markdown content for directory.md.
    """
    drive = _get_drive()
    existing = drive.find_file(_output_folder_id, "directory.md")
    if _dry_run:
        action = "update" if existing else "create"
        log.info("dry_run_skip", action=action, file="directory.md", category="root")
        return f"[dry-run] Would {action} root directory.md."
    if existing:
        drive.update_file(existing["id"], content, "directory.md")
        return "Updated directory.md."
    else:
        drive.write_file(_output_folder_id, "directory.md", content)
        return "Created directory.md."


@tool
def list_folder(path: str = "") -> str:
    """List all files and subfolders at a given path in the knowledge base.

    Use this during indexing to discover the actual contents of a folder
    rather than relying on potentially stale directory.md files.

    Args:
        path: Slash-separated path to the folder (e.g. "projects" or
            "projects/dashboard-redesign"). Leave empty to list the root.

    Returns a formatted listing with item type, name, and modification time.
    """
    drive = _get_drive()
    if path:
        try:
            folder_id = _resolve_folder(path)
        except ValueError:
            return f"Path '{path}' does not exist."
    else:
        folder_id = _output_folder_id

    items = drive.list_files(folder_id)
    if not items:
        return f"'{path or 'root'}' is empty."

    folders = sorted(
        [f for f in items if f.get("mimeType") == "application/vnd.google-apps.folder"],
        key=lambda x: x["name"],
    )
    files = sorted(
        [f for f in items if f.get("mimeType") != "application/vnd.google-apps.folder"],
        key=lambda x: x["name"],
    )

    lines = []
    for f in folders:
        lines.append(f"[folder] {f['name']}  (modified: {f.get('modifiedTime', 'unknown')})")
    for f in files:
        lines.append(f"[file]   {f['name']}  (modified: {f.get('modifiedTime', 'unknown')})")
    return "\n".join(lines)


@tool
def create_new_category(category_name: str) -> str:
    """Create a new topic folder inside a section, or a new section at the root.

    Use this when no existing topic folder fits a message. After creating the
    folder, update the section's directory.md via update_category_summary.

    Args:
        category_name: Slash-separated path for the new folder
            (e.g. "projects/dashboard-redesign" or "health").
    """
    drive = _get_drive()
    parts = category_name.rsplit("/", 1)
    if len(parts) == 2:
        parent_path, folder_name = parts
        try:
            parent_id = _resolve_folder(parent_path)
        except ValueError:
            return f"Parent path '{parent_path}' does not exist."
    else:
        parent_id = _output_folder_id
        folder_name = parts[0]

    existing = drive.find_file(parent_id, folder_name)
    if existing and existing.get("mimeType") == "application/vnd.google-apps.folder":
        return f"Category '{category_name}' already exists."

    if _dry_run:
        log.info("dry_run_skip", action="create_folder", category=category_name)
        return f"[dry-run] Would create category '{category_name}'."

    drive.create_folder(parent_id, folder_name)
    log.info("category_created", category=category_name)
    return f"Created category '{category_name}'."


def get_all_tools() -> list:
    """Return all LangChain tools for registration with the agent."""
    return [
        list_folder,
        read_directory_index,
        read_category_summary,
        read_file,
        write_to_category,
        update_category_summary,
        update_directory_index,
        create_new_category,
    ]
