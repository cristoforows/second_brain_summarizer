from __future__ import annotations

import argparse
import logging
import secrets
import string
from datetime import datetime, timezone
from pathlib import Path

import structlog

from second_brain.agent.agent import build_agent, run_agent, run_agent_index, run_agent_with_prompt
from second_brain.agent.llm import create_llm
from second_brain.core.config import get_settings
from second_brain.services.drive import DriveService
from second_brain.tools.drive_tools import get_all_tools, init_tools
from second_brain.utils.parser import parse_dump

log = structlog.get_logger()


def _init_agent(dry_run: bool = False) -> tuple:
    """Initialize Drive, tools, and agent. Shared by all pipeline entry points."""
    settings = get_settings()
    drive = DriveService(settings.google_service_refresh_token)
    init_tools(drive, settings.output_drive_folder_id, dry_run=dry_run)
    llm = create_llm(settings)
    tools = get_all_tools()
    agent = build_agent(llm, tools)
    return settings, drive, agent


def run_pipeline(date_str: str | None = None, dry_run: bool = False) -> None:
    """Execute the full summarization pipeline for a given date.

    Args:
        date_str: Date string (YYYY-MM-DD) to look for the dump file.
                  Defaults to today in UTC.
    """
    settings, drive, agent = _init_agent(dry_run=dry_run)

    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    log.info("pipeline_start", date=date_str)

    try:
        # --- Find today's dump file ---
        dump_filename = f"{date_str}.md"
        dump_file = drive.find_file(settings.input_drive_folder_id, dump_filename)

        messages = []
        if dump_file is None:
            log.info("no_dump_file_found", filename=dump_filename)
        else:
            log.info("dump_file_found", file_id=dump_file["id"], name=dump_file["name"])
            raw_content = drive.read_file_raw(dump_file["id"], dump_filename)
            messages = parse_dump(raw_content)

        # --- Run agent ---
        if messages:
            log.info("messages_parsed", count=len(messages))
            run_agent(agent, messages)
            log.info("pipeline_complete", date=date_str, messages_processed=len(messages))
            print(f"Processed {len(messages)} messages from {dump_filename}.")
        else:
            log.info("no_messages_running_todo_maintenance", date=date_str)
            from second_brain.agent.prompts import TODO_MAINTENANCE_PROMPT
            run_agent_with_prompt(agent, TODO_MAINTENANCE_PROMPT)
            log.info("todo_maintenance_complete", date=date_str)
            print(f"No messages for {date_str} — ran to-do maintenance.")
    finally:
        drive.log_run_summary()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Second Brain Summarizer — organize messages into a living knowledge base",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date to process (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--prompt", "-p",
        type=str,
        default=None,
        help="Run the agent with a custom prompt instead of a dump file.",
    )
    parser.add_argument(
        "--index",
        action="store_true",
        help="Rebuild Directory.yaml files across the knowledge base.",
    )
    parser.add_argument(
        "--changed",
        nargs="+",
        metavar="PATH",
        default=None,
        help="Paths of recently added or modified files (used with --index).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging to see agent reasoning steps.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full pipeline but skip all Drive write operations.",
    )
    args = parser.parse_args()

    log_path = _configure_logging(verbose=args.verbose, date_str=args.date)
    log.info("log_file", path=str(log_path))

    if args.dry_run:
        log.info("dry_run_mode_enabled")
        print("[dry-run] No changes will be written to Google Drive.")

    if args.prompt:
        _run_prompt(args.prompt, dry_run=args.dry_run)
    elif args.index:
        _run_index(args.changed, dry_run=args.dry_run)
    else:
        run_pipeline(date_str=args.date, dry_run=args.dry_run)


def _configure_logging(verbose: bool = False, date_str: str | None = None) -> Path:
    """Configure structlog + stdlib logging.

    Console respects --verbose (INFO by default, DEBUG when set).
    A DEBUG-level file log is always written to ``tmp/<run_id><date>.log``
    at the project root, so local runs leave a per-run trace on disk.
    Returns the log file path.
    """
    console_level = logging.DEBUG if verbose else logging.INFO

    alphabet = string.ascii_lowercase + string.digits
    run_id = "".join(secrets.choice(alphabet) for _ in range(4))
    date_part = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    project_root = Path(__file__).resolve().parents[2]
    tmp_dir = project_root / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    log_path = tmp_dir / f"{run_id}{date_part}.log"

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processor=structlog.dev.ConsoleRenderer(),
        )
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processor=structlog.dev.ConsoleRenderer(colors=False),
        )
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

    return log_path


def _run_prompt(prompt: str, dry_run: bool = False) -> None:
    """Initialize tools and run the agent with a custom user prompt."""
    _, drive, agent = _init_agent(dry_run=dry_run)
    try:
        run_agent_with_prompt(agent, prompt)
    finally:
        drive.log_run_summary()


def _run_index(changed_files: list[str] | None = None, dry_run: bool = False) -> None:
    """Initialize tools and run the indexer to rebuild Directory.yaml files."""
    _, drive, agent = _init_agent(dry_run=dry_run)
    try:
        run_agent_index(agent, changed_files)
    finally:
        drive.log_run_summary()



if __name__ == "__main__":
    main()
