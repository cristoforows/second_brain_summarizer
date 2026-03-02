from __future__ import annotations

from unittest.mock import MagicMock, patch

from second_brain.main import run_pipeline


_MODULE = "second_brain.main"


@patch(f"{_MODULE}.run_agent")
@patch(f"{_MODULE}.build_agent")
@patch(f"{_MODULE}.create_llm")
@patch(f"{_MODULE}.get_all_tools")
@patch(f"{_MODULE}.init_tools")
@patch(f"{_MODULE}.DriveService")
@patch(f"{_MODULE}.get_settings")
def test_full_pipeline(
    mock_settings: MagicMock,
    mock_drive_cls: MagicMock,
    mock_init_tools: MagicMock,
    mock_get_tools: MagicMock,
    mock_create_llm: MagicMock,
    mock_build_agent: MagicMock,
    mock_run_agent: MagicMock,
    sample_dump_text: str,
) -> None:
    """Pipeline finds the dump file, parses messages, and invokes the agent."""
    settings = MagicMock()
    settings.google_service_refresh_token = "/fake/sa.json"
    settings.input_drive_folder_id = "input-folder"
    settings.output_drive_folder_id = "output-folder"
    mock_settings.return_value = settings

    drive = mock_drive_cls.return_value
    drive.find_file.return_value = {"id": "dump-id", "name": "2025-03-01"}
    drive.read_file_raw.return_value = sample_dump_text

    mock_get_tools.return_value = [MagicMock()]
    mock_run_agent.return_value = {"messages": ["done"]}

    run_pipeline(date_str="2025-03-01")

    # Verify the pipeline steps
    mock_drive_cls.assert_called_once_with("/fake/sa.json")
    mock_init_tools.assert_called_once_with(drive, "output-folder")
    drive.find_file.assert_called_once_with("input-folder", "2025-03-01")
    drive.read_file_raw.assert_called_once_with("dump-id")
    mock_create_llm.assert_called_once_with(settings)
    mock_build_agent.assert_called_once()
    mock_run_agent.assert_called_once()

    # Verify 5 messages were parsed from sample dump
    agent_messages = mock_run_agent.call_args[0][1]
    assert len(agent_messages) == 5


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
) -> None:
    """Pipeline exits early when no dump file is found."""
    settings = MagicMock()
    settings.google_service_refresh_token = "/fake/sa.json"
    settings.input_drive_folder_id = "input-folder"
    settings.output_drive_folder_id = "output-folder"
    mock_settings.return_value = settings

    drive = mock_drive_cls.return_value
    drive.find_file.return_value = None

    run_pipeline(date_str="2025-03-01")

    mock_create_llm.assert_not_called()
    mock_build_agent.assert_not_called()
    mock_run_agent.assert_not_called()


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
) -> None:
    """Pipeline exits early when dump file has no parseable messages."""
    settings = MagicMock()
    settings.google_service_refresh_token = "/fake/sa.json"
    settings.input_drive_folder_id = "input-folder"
    settings.output_drive_folder_id = "output-folder"
    mock_settings.return_value = settings

    drive = mock_drive_cls.return_value
    drive.find_file.return_value = {"id": "dump-id", "name": "2025-03-01"}
    drive.read_file_raw.return_value = "No delimiters here, just plain text."

    run_pipeline(date_str="2025-03-01")

    mock_create_llm.assert_not_called()
    mock_build_agent.assert_not_called()
    mock_run_agent.assert_not_called()
