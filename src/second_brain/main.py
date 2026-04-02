from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

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

    # --- Find today's dump file ---
    dump_filename = f"{date_str}.md"
    dump_file = drive.find_file(settings.input_drive_folder_id, dump_filename)
    if dump_file is None:
        log.warning("no_dump_file_found", filename=dump_filename)
        print(f"No dump file found for {date_str} — nothing to process.")
        return

    log.info("dump_file_found", file_id=dump_file["id"], name=dump_file["name"])

    # --- Parse messages ---
    raw_content = drive.read_file_raw(dump_file["id"])
    messages = parse_dump(raw_content)

    if not messages:
        log.warning("no_messages_parsed", filename=dump_filename)
        print(f"Dump file {dump_filename} contained no messages.")
        return

    log.info("messages_parsed", count=len(messages))

    # --- Run agent ---
    result = run_agent(agent, messages)

    log.info(
        "pipeline_complete",
        date=date_str,
        messages_processed=len(messages),
    )
    print(f"Processed {len(messages)} messages from {dump_filename}.")


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
        help="Rebuild directory.md files across the knowledge base.",
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

    _configure_logging(verbose=args.verbose)

    if args.dry_run:
        log.info("dry_run_mode_enabled")
        print("[dry-run] No changes will be written to Google Drive.")

    if args.prompt:
        _run_prompt(args.prompt, dry_run=args.dry_run)
    elif args.index:
        _run_index(args.changed, dry_run=args.dry_run)
    else:
        run_pipeline(date_str=args.date, dry_run=args.dry_run)


def _configure_logging(verbose: bool = False) -> None:
    """Configure structlog with the appropriate log level.

    Default level is INFO, which logs pipeline milestones.
    Verbose mode (DEBUG) additionally logs agent reasoning steps,
    tool calls, and tool results.
    """
    level = logging.DEBUG if verbose else logging.INFO

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
    )


def _run_prompt(prompt: str, dry_run: bool = False) -> None:
    """Initialize tools and run the agent with a custom user prompt."""
    _, _, agent = _init_agent(dry_run=dry_run)
    run_agent_with_prompt(agent, prompt)


def _run_index(changed_files: list[str] | None = None, dry_run: bool = False) -> None:
    """Initialize tools and run the indexer to rebuild directory.md files."""
    _, _, agent = _init_agent(dry_run=dry_run)
    run_agent_index(agent, changed_files)



if __name__ == "__main__":
    main()
