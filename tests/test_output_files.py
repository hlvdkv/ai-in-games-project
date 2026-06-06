"""Tests verifying the consistency and correctness of generated output files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from questgen.pddl import load_domain, load_problem, parse_problem_text


class TestRequiredFilesExist:
    REQUIRED_FILES = {
        "domain.pddl",
        "prompt.txt",
        "series.json",
        "generation_meta.json",
    }

    def test_all_required_files_present(self, generated_series_dir: Path):
        for name in self.REQUIRED_FILES:
            assert (generated_series_dir / name).exists(), f"Missing {name}"

    def test_at_least_one_quest_pair(self, generated_series_dir: Path):
        json_files = list(generated_series_dir.glob("quest_*.json"))
        assert json_files, "No quest JSON files found"
        for json_path in json_files:
            pddl_path = json_path.with_suffix(".pddl")
            plan_path = json_path.with_suffix(".plan")
            assert pddl_path.exists(), f"Missing PDDL for {json_path.name}"
            assert plan_path.exists(), f"Missing plan for {json_path.name}"


class TestPromptFile:
    def test_is_non_empty(self, generated_series_dir: Path):
        content = (generated_series_dir / "prompt.txt").read_text(encoding="utf-8")
        assert content.strip()


class TestDomainFile:
    def test_loads_without_error(self, generated_series_dir: Path):
        domain_path = generated_series_dir / "domain.pddl"
        domain = load_domain(domain_path)
        assert domain.name == "mythic_quest"
        assert len(domain.actions) > 0


class TestQuestJsonFiles:
    def test_all_are_valid_json(self, generated_series_dir: Path):
        for json_path in generated_series_dir.glob("quest_*.json"):
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert isinstance(data, dict)

    def test_required_top_level_fields(self, generated_series_dir: Path):
        required = {"id", "title", "synopsis", "steps", "objects", "expected_plan", "verified_plan", "repairs"}
        for json_path in generated_series_dir.glob("quest_*.json"):
            data = json.loads(json_path.read_text(encoding="utf-8"))
            missing = required - set(data.keys())
            assert not missing, f"{json_path.name} missing fields: {missing}"

    def test_steps_is_non_empty_list(self, generated_series_dir: Path):
        for json_path in generated_series_dir.glob("quest_*.json"):
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert isinstance(data["steps"], list)
            assert len(data["steps"]) > 0

    def test_objects_is_non_empty_list(self, generated_series_dir: Path):
        for json_path in generated_series_dir.glob("quest_*.json"):
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert isinstance(data["objects"], list)
            assert len(data["objects"]) > 0

    def test_all_objects_have_id_type_name(self, generated_series_dir: Path):
        for json_path in generated_series_dir.glob("quest_*.json"):
            data = json.loads(json_path.read_text(encoding="utf-8"))
            for obj in data["objects"]:
                assert "id" in obj
                assert "type" in obj
                assert "name" in obj
                assert obj["type"] in {"location", "item", "npc", "enemy", "gate"}

    def test_verified_plan_matches_expected(self, generated_series_dir: Path):
        for json_path in generated_series_dir.glob("quest_*.json"):
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert data["verified_plan"] == data["expected_plan"]

    def test_expected_plan_count_matches_steps(self, generated_series_dir: Path):
        for json_path in generated_series_dir.glob("quest_*.json"):
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert len(data["expected_plan"]) == len(data["steps"])

    def test_dialogues_present_for_npcs(self, generated_series_dir: Path):
        for json_path in generated_series_dir.glob("quest_*.json"):
            data = json.loads(json_path.read_text(encoding="utf-8"))
            for obj in data.get("objects", []):
                if obj["type"] == "npc":
                    assert "dialogues" in obj, f"NPC {obj['id']} missing dialogues in {json_path.name}"
                    assert obj["dialogues"], f"NPC {obj['id']} has empty dialogues in {json_path.name}"

    def test_start_location_defined(self, generated_series_dir: Path):
        for json_path in generated_series_dir.glob("quest_*.json"):
            data = json.loads(json_path.read_text(encoding="utf-8"))
            assert "start_location" in data
            assert data["start_location"]


class TestQuestPddlFiles:
    def test_all_load_without_error(self, generated_series_dir: Path):
        for pddl_path in generated_series_dir.glob("quest_*.pddl"):
            problem = load_problem(pddl_path)
            assert problem.name
            assert problem.domain_name == "mythic_quest"
            assert problem.init
            assert problem.goal_pos

    def test_goal_is_final_stage(self, generated_series_dir: Path):
        for pddl_path in generated_series_dir.glob("quest_*.pddl"):
            problem = load_problem(pddl_path)
            json_path = pddl_path.with_suffix(".json")
            data = json.loads(json_path.read_text(encoding="utf-8"))
            final_stage = f"{data['id']}-s{len(data['steps'])}"
            assert ("current-stage", final_stage) in problem.goal_pos

    def test_objects_match_json_objects(self, generated_series_dir: Path):
        for pddl_path in generated_series_dir.glob("quest_*.pddl"):
            problem = load_problem(pddl_path)
            json_path = pddl_path.with_suffix(".json")
            data = json.loads(json_path.read_text(encoding="utf-8"))
            json_object_ids = {obj["id"] for obj in data["objects"]}
            # Gather all PDDL object ids across types
            pddl_object_ids = set()
            for objs in problem.objects_by_type.values():
                pddl_object_ids.update(objs)
            # JSON objects should be a subset of PDDL objects
            # (PDDL also has stage objects which JSON does not list in objects[])
            missing = json_object_ids - pddl_object_ids
            assert not missing, f"{pddl_path.name} missing objects: {missing}"

    def test_init_contains_hero_at(self, generated_series_dir: Path):
        for pddl_path in generated_series_dir.glob("quest_*.pddl"):
            problem = load_problem(pddl_path)
            assert any(atom[0] == "hero-at" for atom in problem.init)

    def test_init_contains_threat_active(self, generated_series_dir: Path):
        for pddl_path in generated_series_dir.glob("quest_*.pddl"):
            problem = load_problem(pddl_path)
            assert ("threat-active",) in problem.init


class TestPlanFiles:
    def test_plan_matches_verified_plan(self, generated_series_dir: Path):
        for plan_path in generated_series_dir.glob("quest_*.plan"):
            json_path = plan_path.with_suffix(".json")
            data = json.loads(json_path.read_text(encoding="utf-8"))
            plan_lines = plan_path.read_text(encoding="utf-8").strip().splitlines()
            assert plan_lines == data["verified_plan"]

    def test_plan_is_non_empty(self, generated_series_dir: Path):
        for plan_path in generated_series_dir.glob("quest_*.plan"):
            content = plan_path.read_text(encoding="utf-8").strip()
            assert content

    def test_plan_actions_match_steps(self, generated_series_dir: Path):
        for plan_path in generated_series_dir.glob("quest_*.plan"):
            json_path = plan_path.with_suffix(".json")
            data = json.loads(json_path.read_text(encoding="utf-8"))
            plan_lines = plan_path.read_text(encoding="utf-8").strip().splitlines()
            assert len(plan_lines) == len(data["steps"])


class TestSeriesJson:
    def test_is_valid_json(self, generated_series_dir: Path):
        data = json.loads((generated_series_dir / "series.json").read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_has_title_and_premise(self, generated_series_dir: Path):
        data = json.loads((generated_series_dir / "series.json").read_text(encoding="utf-8"))
        assert data.get("series_title")
        assert data.get("premise")

    def test_quests_match_individual_files(self, generated_series_dir: Path):
        series = json.loads((generated_series_dir / "series.json").read_text(encoding="utf-8"))
        json_files = sorted(generated_series_dir.glob("quest_*.json"))
        assert len(series["quests"]) == len(json_files)
        for index, quest in enumerate(series["quests"], start=1):
            expected_prefix = f"quest_{index:02d}_{quest['id']}"
            expected_json = generated_series_dir / f"{expected_prefix}.json"
            assert expected_json.exists()


class TestGenerationMeta:
    def test_is_valid_json(self, generated_series_dir: Path):
        data = json.loads((generated_series_dir / "generation_meta.json").read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_has_required_fields(self, generated_series_dir: Path):
        data = json.loads((generated_series_dir / "generation_meta.json").read_text(encoding="utf-8"))
        assert "model" in data
        assert "quest_count" in data
        assert "files" in data
        assert isinstance(data["files"], list)
        assert len(data["files"]) > 0

    def test_quest_count_matches_actual(self, generated_series_dir: Path):
        data = json.loads((generated_series_dir / "generation_meta.json").read_text(encoding="utf-8"))
        quest_jsons = list(generated_series_dir.glob("quest_*.json"))
        assert data["quest_count"] == len(quest_jsons)

    def test_files_lists_all_existing(self, generated_series_dir: Path):
        data = json.loads((generated_series_dir / "generation_meta.json").read_text(encoding="utf-8"))
        for filename in data["files"]:
            assert (generated_series_dir / filename).exists(), f"{filename} listed in meta but missing"
