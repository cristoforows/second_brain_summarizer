from __future__ import annotations

from unittest.mock import MagicMock, patch

from second_brain.main import run_pipeline


_MODULE = "second_brain.main"


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.google_service_refresh_token = "/fake/sa.json"
    settings.input_drive_folder_id = "input-folder"
    settings.output_drive_folder_id = "output-folder"
    # Empty telegram config so _init_agent skips telegram setup and
    # send_notification short-circuits without an HTTP call.
    settings.telegram_outbound_url = ""
    settings.telegram_outbound_secret = ""
    settings.telegram_chat_id = ""
    return settings


@patch(f"{_MODULE}.run_agent_with_prompt")
@patch(f"{_MODULE}.run_agent")
@patch(f"{_MODULE}.build_agent")
@patch(f"{_MODULE}.create_llm")
@patch(f"{_MODULE}.init_tools")
@patch(f"{_MODULE}.DriveService")
@patch(f"{_MODULE}.get_settings")
def test_full_pipeline(
    mock_settings: MagicMock,
    mock_drive_cls: MagicMock,
    mock_init_tools: MagicMock,
    mock_create_llm: MagicMock,
    mock_build_agent: MagicMock,
    mock_run_agent: MagicMock,
    mock_run_agent_with_prompt: MagicMock,
    sample_dump_text: str,
) -> None:
    """Pipeline finds the dump file, parses messages, and invokes the agent."""
    mock_settings.return_value = _make_settings()

    drive = mock_drive_cls.return_value
    drive.find_file.return_value = {"id": "dump-id", "name": "2025-03-01"}
    drive.read_file_raw.return_value = sample_dump_text
    drive._updates = []

    mock_run_agent.return_value = {"messages": ["done"]}

    run_pipeline(date_str="2025-03-01")

    # Verify the pipeline steps
    mock_drive_cls.assert_called_once_with("/fake/sa.json")
    mock_init_tools.assert_called_once_with(drive, "output-folder", dry_run=False)
    drive.find_file.assert_any_call("input-folder", "2025-03-01.md")
    drive.read_file_raw.assert_any_call("dump-id", "2025-03-01.md")
    mock_create_llm.assert_called_once()
    mock_build_agent.assert_called_once()
    mock_run_agent.assert_called_once()
    mock_run_agent_with_prompt.assert_not_called()

    # Verify 5 messages were parsed from sample dump
    agent_messages = mock_run_agent.call_args[0][1]
    assert len(agent_messages) == 5


@patch(f"{_MODULE}.run_agent_with_prompt")
@patch(f"{_MODULE}.run_agent")
@patch(f"{_MODULE}.build_agent")
@patch(f"{_MODULE}.create_llm")
@patch(f"{_MODULE}.init_tools")
@patch(f"{_MODULE}.DriveService")
@patch(f"{_MODULE}.get_settings")
def test_pipeline_no_dump_file(
    mock_settings: MagicMock,
    mock_drive_cls: MagicMock,
    mock_init_tools: MagicMock,
    mock_create_llm: MagicMock,
    mock_build_agent: MagicMock,
    mock_run_agent: MagicMock,
    mock_run_agent_with_prompt: MagicMock,
) -> None:
    """When no dump file exists, the pipeline runs to-do maintenance instead."""
    mock_settings.return_value = _make_settings()

    drive = mock_drive_cls.return_value
    drive.find_file.return_value = None
    drive._updates = []

    run_pipeline(date_str="2025-03-01")

    # Agent is still built, but invoked via the maintenance prompt path.
    mock_create_llm.assert_called_once()
    mock_build_agent.assert_called_once()
    mock_run_agent.assert_not_called()
    mock_run_agent_with_prompt.assert_called_once()


@patch(f"{_MODULE}.run_agent_with_prompt")
@patch(f"{_MODULE}.run_agent")
@patch(f"{_MODULE}.build_agent")
@patch(f"{_MODULE}.create_llm")
@patch(f"{_MODULE}.init_tools")
@patch(f"{_MODULE}.DriveService")
@patch(f"{_MODULE}.get_settings")
def test_pipeline_empty_dump_file(
    mock_settings: MagicMock,
    mock_drive_cls: MagicMock,
    mock_init_tools: MagicMock,
    mock_create_llm: MagicMock,
    mock_build_agent: MagicMock,
    mock_run_agent: MagicMock,
    mock_run_agent_with_prompt: MagicMock,
) -> None:
    """A dump file with no parseable messages still triggers to-do maintenance."""
    mock_settings.return_value = _make_settings()

    drive = mock_drive_cls.return_value
    drive.find_file.return_value = {"id": "dump-id", "name": "2025-03-01"}
    drive.read_file_raw.return_value = "No delimiters here, just plain text."
    drive._updates = []

    run_pipeline(date_str="2025-03-01")

    mock_run_agent.assert_not_called()
    mock_run_agent_with_prompt.assert_called_once()
