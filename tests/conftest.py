from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_dump_path() -> Path:
    return FIXTURES_DIR / "sample_dump.md"


@pytest.fixture
def sample_dump_text(sample_dump_path: Path) -> str:
    return sample_dump_path.read_text()
