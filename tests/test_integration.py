"""Integration tests for the full quest generation and playback pipeline."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pytest

from questgen.generator import compile_and_verify, fallback_series, normalize_series, write_series
from questgen.play import play_series
from questgen.verify import verify_series


class TestFullPipeline:
    def test_fallback_generates_verifiable_series(self, fresh_tmp_dir: Path):
        prompt = "Integration test prompt"
        series = normalize_series(fallback_series(prompt, quests=3), prompt)
        series, quest_json, quest_pddl, plans = compile_and_verify(series)
        write_series(
            series, quest_json, quest_pddl, plans,
            prompt=prompt,
            model="integration-test",
            out_dir=fresh_tmp_dir,
            used_fallback=True,
        )
        assert verify_series(fresh_tmp_dir) is True

    def test_verify_detects_missing_domain(self, fresh_tmp_dir: Path):
        # Create an empty dir without domain.pddl
        assert verify_series(fresh_tmp_dir) is False

    def test_verify_detects_no_quests(self, fresh_tmp_dir: Path):
        # Put a domain but no quest pairs
        (fresh_tmp_dir / "domain.pddl").write_text(
            "(define (domain mythic_quest) (:requirements :strips :typing) (:types location))",
            encoding="utf-8",
        )
        assert verify_series(fresh_tmp_dir) is False


class TestAutoPlaythrough:
    def test_auto_playthrough_completes(self, generated_series_dir: Path):
        # Capture stdout to avoid printing during tests
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            play_series(generated_series_dir, auto=True)
        except Exception as exc:
            pytest.fail(f"Auto playthrough raised an exception: {exc}")
        finally:
            sys.stdout = old_stdout

    def test_play_single_quest(self, generated_series_dir: Path):
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            play_series(generated_series_dir, auto=True, only_quest=1)
        except Exception as exc:
            pytest.fail(f"Single quest playthrough raised an exception: {exc}")
        finally:
            sys.stdout = old_stdout

    def test_play_with_missing_domain_raises(self, fresh_tmp_dir: Path):
        with pytest.raises(FileNotFoundError):
            play_series(fresh_tmp_dir)


class TestIdempotency:
    def test_regenerating_same_series_produces_same_plans(self, fresh_tmp_dir: Path):
        prompt = "Idempotency test"
        series1 = normalize_series(fallback_series(prompt, quests=3), prompt)
        series1, qj1, qp1, plans1 = compile_and_verify(series1)

        series2 = normalize_series(fallback_series(prompt, quests=3), prompt)
        series2, qj2, qp2, plans2 = compile_and_verify(series2)

        for qid in plans1:
            assert plans1[qid] == plans2[qid]

    def test_verified_plan_is_solvable(self, generated_series_dir: Path):
        from questgen.pddl import load_domain, load_problem, solve

        domain = load_domain(generated_series_dir / "domain.pddl")
        for json_path in generated_series_dir.glob("quest_*.json"):
            pddl_path = json_path.with_suffix(".pddl")
            problem = load_problem(pddl_path)
            plan = solve(domain, problem, max_depth=80)
            assert plan is not None, f"{pddl_path.name} should be solvable"
