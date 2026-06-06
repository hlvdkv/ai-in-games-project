"""Shared fixtures for questgen tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from questgen.domain import DOMAIN_NAME, DOMAIN_PDDL
from questgen.generator import (
    compile_and_verify,
    fallback_series,
    normalize_series,
)
from questgen.pddl import load_domain, parse_domain_text, parse_problem_text


@pytest.fixture(scope="session")
def domain():
    """Parsed shared PDDL domain."""
    return parse_domain_text(DOMAIN_PDDL)


@pytest.fixture(scope="session")
def domain_name():
    return DOMAIN_NAME


@pytest.fixture
def sample_quest():
    """First quest from the deterministic fallback series."""
    series = fallback_series("Test prompt for pytest fixtures", quests=3)
    return series["quests"][0]


@pytest.fixture
def normalized_series():
    """Fully normalized fallback series ready for compilation."""
    prompt = "Test prompt for pytest fixtures"
    series = normalize_series(fallback_series(prompt, quests=3), prompt)
    return series


@pytest.fixture(scope="session")
def generated_series_dir(tmp_path_factory) -> Path:
    """Generate a full fallback series once per session into a temp dir."""
    out_dir = tmp_path_factory.mktemp("questgen_series")
    prompt = "Test prompt for generated series"
    series = normalize_series(fallback_series(prompt, quests=3), prompt)
    series, quest_json, quest_pddl, plans = compile_and_verify(series)
    from questgen.domain import DOMAIN_PDDL
    from questgen.generator import write_series

    write_series(
        series,
        quest_json,
        quest_pddl,
        plans,
        prompt,
        model="test-model",
        out_dir=out_dir,
        used_fallback=True,
    )
    return out_dir


@pytest.fixture
def fresh_tmp_dir(tmp_path: Path) -> Path:
    """Fresh empty temporary directory for a single test."""
    return tmp_path
