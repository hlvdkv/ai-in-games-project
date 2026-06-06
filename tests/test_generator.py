"""Tests for the quest generator, repair pass, and PDDL compilation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from questgen.domain import DOMAIN_NAME, DOMAIN_PDDL
from questgen.generator import (
    build_init_facts,
    build_objects,
    build_problem_pddl,
    compile_and_verify,
    enrich_quest_json,
    expected_plan,
    fallback_series,
    normalize_quest_ids,
    normalize_series,
    repair_quest_schema,
    write_series,
)
from questgen.pddl import parse_domain_text, parse_problem_text, solve


class TestFallbackSeries:
    def test_returns_three_quests(self):
        series = fallback_series("Test prompt", quests=3)
        assert len(series["quests"]) == 3

    def test_first_quest_has_steps(self):
        series = fallback_series("Test prompt", quests=3)
        quest = series["quests"][0]
        assert quest["steps"]
        assert all("action" in step for step in quest["steps"])

    def test_prompt_preserved(self):
        series = fallback_series("My custom prompt", quests=3)
        assert series["premise"] == "My custom prompt"

    def test_quest_count_respected(self):
        series = fallback_series("Test", quests=2)
        assert len(series["quests"]) == 2


class TestRepairQuestSchema:
    def test_infers_start_location(self, sample_quest):
        quest = sample_quest.copy()
        del quest["start_location"]
        repairs = repair_quest_schema(quest)
        assert quest["start_location"]
        assert "inferred missing start_location" in repairs

    def test_adds_missing_locations(self):
        quest = {
            "id": "test-quest",
            "steps": [
                {"action": "travel", "from": "a", "to": "b"},
            ],
            "locations": [],
            "items": [],
            "npcs": [],
            "enemies": [],
        }
        repairs = repair_quest_schema(quest)
        location_ids = {loc["id"] for loc in quest["locations"]}
        assert "a" in location_ids
        assert "b" in location_ids
        assert any("added missing location" in r for r in repairs)

    def test_adds_missing_npc_for_talk(self):
        quest = {
            "id": "test-quest",
            "steps": [
                {"action": "talk", "npc": "wise-old-man", "location": "village"},
            ],
            "locations": [{"id": "village", "name": "Village"}],
            "items": [],
            "npcs": [],
            "enemies": [],
        }
        repair_quest_schema(quest)
        npc_ids = {n["id"] for n in quest["npcs"]}
        assert "wise-old-man" in npc_ids

    def test_adds_dialogue_for_talk(self):
        quest = {
            "id": "test-quest",
            "steps": [
                {"action": "talk", "npc": "guide", "location": "village", "dialogue": "Follow the path."},
            ],
            "locations": [{"id": "village", "name": "Village"}],
            "items": [],
            "npcs": [],
            "enemies": [],
        }
        repair_quest_schema(quest)
        guide = next(n for n in quest["npcs"] if n["id"] == "guide")
        talk_dialogues = [d for d in guide.get("dialogues", []) if d["trigger"] == "talk"]
        assert talk_dialogues
        assert talk_dialogues[0]["text"] == "Follow the path."

    def test_adds_dialogue_for_give(self):
        quest = {
            "id": "test-quest",
            "steps": [
                {"action": "give", "item": "key", "npc": "guard", "location": "gate"},
            ],
            "locations": [{"id": "gate", "name": "Gate"}],
            "items": [],
            "npcs": [],
            "enemies": [],
        }
        repair_quest_schema(quest)
        guard = next(n for n in quest["npcs"] if n["id"] == "guard")
        give_dialogues = [d for d in guard.get("dialogues", []) if d["trigger"] == "give:key"]
        assert give_dialogues

    def test_adds_consequence_locations(self):
        quest = {
            "id": "test-quest",
            "steps": [
                {"action": "travel", "from": "start", "to": "end"},
            ],
            "locations": [{"id": "start", "name": "Start"}, {"id": "end", "name": "End"}],
            "items": [],
            "npcs": [],
            "enemies": [],
            "consequences": {
                "hidden_routes": [
                    {"item": "map", "from": "start", "to": "secret"}
                ]
            },
        }
        repairs = repair_quest_schema(quest)
        location_ids = {loc["id"] for loc in quest["locations"]}
        assert "secret" in location_ids
        assert any("added consequence location" in r for r in repairs)

    def test_adds_provocation_enemy(self):
        quest = {
            "id": "test-quest",
            "steps": [
                {"action": "travel", "from": "start", "to": "village"},
            ],
            "locations": [{"id": "start", "name": "Start"}, {"id": "village", "name": "Village"}],
            "items": [],
            "npcs": [],
            "enemies": [],
            "consequences": {
                "provocations": [
                    {"npc": "thief", "enemy": "thug", "location": "village"}
                ]
            },
        }
        repair_quest_schema(quest)
        enemy_ids = {e["id"] for e in quest["enemies"]}
        assert "thug" in enemy_ids
        thug = next(e for e in quest["enemies"] if e["id"] == "thug")
        assert thug.get("optional") is True
        assert thug.get("hostile") is False


class TestNormalizeQuestIds:
    def test_sluggifies_ids(self):
        quest = {
            "id": "quest-1",
            "locations": [{"id": "Old Well"}, {"id": "Village Square"}],
            "items": [{"id": "Silver Knife"}],
            "npcs": [{"id": "Elder Mira"}],
            "enemies": [],
            "steps": [
                {"action": "travel", "from": "Old Well", "to": "Village Square"},
            ],
        }
        normalize_quest_ids(quest)
        loc_ids = {loc["id"] for loc in quest["locations"]}
        assert "old-well" in loc_ids
        assert "village-square" in loc_ids

    def test_preserves_already_slugified_ids(self):
        quest = {
            "id": "quest-1",
            "locations": [{"id": "old-well"}],
            "items": [],
            "npcs": [],
            "enemies": [],
            "steps": [],
        }
        normalize_quest_ids(quest)
        assert quest["id"] == "quest-1"


class TestBuildInitFacts:
    def test_contains_hero_at_start(self, sample_quest):
        facts = build_init_facts(sample_quest)
        assert ("hero-at", sample_quest["start_location"]) in facts

    def test_contains_current_stage_zero(self, sample_quest):
        facts = build_init_facts(sample_quest)
        assert ("current-stage", f"{sample_quest['id']}-s0") in facts

    def test_contains_next_stages(self, sample_quest):
        facts = build_init_facts(sample_quest)
        steps = sample_quest["steps"]
        for i in range(len(steps)):
            assert ("next-stage", f"{sample_quest['id']}-s{i}", f"{sample_quest['id']}-s{i+1}") in facts

    def test_contains_step_predicates(self, sample_quest):
        facts = build_init_facts(sample_quest)
        # Should have at least one step predicate matching the first action
        first_action = sample_quest["steps"][0]["action"]
        step_predicates = {f[0] for f in facts}
        assert f"{first_action}-step" in step_predicates

    def test_contains_threat_active(self, sample_quest):
        facts = build_init_facts(sample_quest)
        assert ("threat-active",) in facts

    def test_optional_item_flag(self, sample_quest):
        facts = build_init_facts(sample_quest)
        for item in sample_quest.get("items", []):
            if item.get("optional"):
                assert ("optional-item", item["id"]) in facts

    def test_hidden_route_fact(self):
        quest = {
            "id": "test-q",
            "start_location": "start",
            "locations": [{"id": "start"}, {"id": "end"}],
            "items": [{"id": "map"}],
            "npcs": [],
            "enemies": [],
            "steps": [],
            "consequences": {
                "hidden_routes": [
                    {"item": "map", "from": "start", "to": "end"}
                ]
            },
        }
        facts = build_init_facts(quest)
        assert ("hidden-route", "map", "start", "end") in facts


class TestBuildObjects:
    def test_includes_all_types(self, sample_quest):
        objects = build_objects(sample_quest)
        assert "location" in objects
        assert "stage" in objects
        for step in sample_quest["steps"]:
            if step["action"] == "unlock":
                assert step["gate"] in objects["gate"]

    def test_stage_count(self, sample_quest):
        objects = build_objects(sample_quest)
        stages = objects["stage"]
        expected_count = len(sample_quest["steps"]) + 1
        assert len(stages) == expected_count


class TestBuildProblemPddl:
    def test_valid_pddl_syntax(self, sample_quest):
        text = build_problem_pddl(sample_quest)
        assert text.startswith("(define (problem")
        problem = parse_problem_text(text)
        assert problem.name == sample_quest["id"]

    def test_includes_domain_name(self, sample_quest):
        text = build_problem_pddl(sample_quest)
        assert f"(:domain {DOMAIN_NAME})" in text

    def test_goal_is_final_stage(self, sample_quest):
        text = build_problem_pddl(sample_quest)
        final_stage = f"{sample_quest['id']}-s{len(sample_quest['steps'])}"
        assert f"(current-stage {final_stage})" in text


class TestExpectedPlan:
    def test_matches_step_count(self, sample_quest):
        plan = expected_plan(sample_quest)
        assert len(plan) == len(sample_quest["steps"])

    def test_signatures_are_well_formed(self, sample_quest):
        plan = expected_plan(sample_quest)
        for sig in plan:
            assert sig.startswith("(") and sig.endswith(")")
            parts = sig[1:-1].split()
            assert len(parts) >= 2  # action name + at least one arg

    def test_first_action_matches_first_step(self, sample_quest):
        plan = expected_plan(sample_quest)
        first_step = sample_quest["steps"][0]
        assert first_step["action"] in plan[0]


class TestCompileAndVerify:
    def test_produces_plans(self, normalized_series):
        series, quest_json, quest_pddl, plans = compile_and_verify(normalized_series)
        assert len(plans) == len(series["quests"])
        for qid, plan in plans.items():
            assert plan is not None
            assert len(plan) > 0

    def test_plans_match_expected(self, normalized_series):
        series, quest_json, quest_pddl, plans = compile_and_verify(normalized_series)
        for quest in series["quests"]:
            assert quest["verified_plan"] == quest["expected_plan"]

    def test_repairs_empty_for_fallback(self, normalized_series):
        # Fallback series is already well-formed, so repairs should be minimal or empty
        series, quest_json, quest_pddl, plans = compile_and_verify(normalized_series)
        for quest in series["quests"]:
            assert "repairs" in quest


class TestEnrichQuestJson:
    def test_adds_objects(self, sample_quest):
        quest = sample_quest.copy()
        enrich_quest_json(quest, ["(travel a b s0 s1)"], [])
        assert "objects" in quest
        object_ids = {o["id"] for o in quest["objects"]}
        for loc in sample_quest["locations"]:
            assert loc["id"] in object_ids

    def test_adds_verified_plan(self, sample_quest):
        quest = sample_quest.copy()
        enrich_quest_json(quest, ["(action1)", "(action2)"], ["repair1"])
        assert quest["verified_plan"] == ["(action1)", "(action2)"]

    def test_adds_repairs(self, sample_quest):
        quest = sample_quest.copy()
        enrich_quest_json(quest, [], ["added location x"])
        assert quest["repairs"] == ["added location x"]


class TestWriteSeries:
    def test_creates_all_files(self, fresh_tmp_dir, normalized_series):
        series = normalized_series
        series, quest_json, quest_pddl, plans = compile_and_verify(series)
        write_series(
            series,
            quest_json,
            quest_pddl,
            plans,
            prompt="Test prompt",
            model="test-model",
            out_dir=fresh_tmp_dir,
            used_fallback=True,
        )
        assert (fresh_tmp_dir / "domain.pddl").exists()
        assert (fresh_tmp_dir / "prompt.txt").exists()
        assert (fresh_tmp_dir / "series.json").exists()
        assert (fresh_tmp_dir / "generation_meta.json").exists()
        for index, quest in enumerate(series["quests"], start=1):
            prefix = f"quest_{index:02d}_{quest['id']}"
            assert (fresh_tmp_dir / f"{prefix}.json").exists()
            assert (fresh_tmp_dir / f"{prefix}.pddl").exists()
            assert (fresh_tmp_dir / f"{prefix}.plan").exists()

    def test_prompt_file_content(self, fresh_tmp_dir, normalized_series):
        series = normalized_series
        series, quest_json, quest_pddl, plans = compile_and_verify(series)
        write_series(
            series, quest_json, quest_pddl, plans,
            prompt="Hello world prompt",
            model="test-model",
            out_dir=fresh_tmp_dir,
            used_fallback=False,
        )
        content = (fresh_tmp_dir / "prompt.txt").read_text(encoding="utf-8")
        assert "Hello world prompt" in content

    def test_domain_file_content(self, fresh_tmp_dir, normalized_series):
        series = normalized_series
        series, quest_json, quest_pddl, plans = compile_and_verify(series)
        write_series(
            series, quest_json, quest_pddl, plans,
            prompt="Test",
            model="test-model",
            out_dir=fresh_tmp_dir,
            used_fallback=False,
        )
        content = (fresh_tmp_dir / "domain.pddl").read_text(encoding="utf-8")
        assert "(define (domain mythic_quest)" in content

    def test_generation_meta_fields(self, fresh_tmp_dir, normalized_series):
        series = normalized_series
        series, quest_json, quest_pddl, plans = compile_and_verify(series)
        write_series(
            series, quest_json, quest_pddl, plans,
            prompt="Test",
            model="my-model",
            out_dir=fresh_tmp_dir,
            used_fallback=False,
        )
        meta = json.loads((fresh_tmp_dir / "generation_meta.json").read_text(encoding="utf-8"))
        assert meta["model"] == "my-model"
        assert meta["used_fallback"] is False
        assert meta["quest_count"] == len(series["quests"])
        assert "files" in meta


class TestExpectedPlanEdgeCases:
    def test_skips_unknown_actions(self):
        quest = {
            "id": "test-q",
            "steps": [
                {"action": "travel", "from": "a", "to": "b"},
                {"action": "unknown-action", "foo": "bar"},
            ],
        }
        plan = expected_plan(quest)
        assert len(plan) == 1
        assert "travel" in plan[0]


class TestNormalizeSeriesEdgeCases:
    def test_filters_unsupported_actions(self):
        series = {
            "series_title": "Test",
            "premise": "Test premise",
            "quests": [
                {
                    "id": "q1",
                    "title": "Quest",
                    "steps": [
                        {"action": "travel", "from": "a", "to": "b"},
                        {"action": "dance", "foo": "bar"},  # unsupported
                    ],
                    "locations": [{"id": "a"}, {"id": "b"}],
                    "items": [],
                    "npcs": [],
                    "enemies": [],
                }
            ],
        }
        result = normalize_series(series, "Test premise")
        assert len(result["quests"]) == 1
        assert len(result["quests"][0]["steps"]) == 1
        assert result["quests"][0]["steps"][0]["action"] == "travel"

    def test_drops_quest_with_no_steps(self):
        series = {
            "series_title": "Test",
            "premise": "Test premise",
            "quests": [
                {
                    "id": "q1",
                    "title": "Quest",
                    "steps": [{"action": "dance"}],  # unsupported -> empty after filter
                    "locations": [],
                    "items": [],
                    "npcs": [],
                    "enemies": [],
                }
            ],
        }
        result = normalize_series(series, "Test premise")
        # Should fall back to fallback_series because no valid quests remain
        assert len(result["quests"]) == 3
