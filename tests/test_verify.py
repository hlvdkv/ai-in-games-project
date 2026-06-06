"""Tests for the verify module CLI and edge cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from questgen.verify import build_arg_parser, main, verify_series


class TestVerifyMain:
    def test_main_with_valid_series(self, generated_series_dir: Path):
        code = main(["--series", str(generated_series_dir)])
        assert code == 0

    def test_main_with_missing_domain(self, fresh_tmp_dir: Path):
        code = main(["--series", str(fresh_tmp_dir)])
        assert code == 1

    def test_main_with_no_quests(self, fresh_tmp_dir: Path):
        (fresh_tmp_dir / "domain.pddl").write_text(
            "(define (domain mythic_quest) (:requirements :strips :typing) (:types location))",
            encoding="utf-8",
        )
        code = main(["--series", str(fresh_tmp_dir)])
        assert code == 1

    def test_arg_parser_defaults(self):
        parser = build_arg_parser()
        args = parser.parse_args([])
        assert args.series == "quests/generated/ash_bell"
