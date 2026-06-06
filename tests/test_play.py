"""Tests for the text-based quest player helpers."""

from __future__ import annotations

import pytest

from questgen.play import (
    action_label,
    consequence_text,
    current_location,
    description_of,
    dialogue_for_action,
    examine_text,
    facts_with,
    inventory,
    is_wounded,
    name_of,
    object_index,
    step_for_action,
)
from questgen.pddl import GroundAction


class TestObjectIndex:
    def test_indexes_locations(self):
        quest = {
            "locations": [{"id": "village", "name": "Village"}],
            "items": [],
            "npcs": [],
            "enemies": [],
        }
        idx = object_index(quest)
        assert "village" in idx
        assert idx["village"]["name"] == "Village"

    def test_indexes_objects_field(self):
        quest = {
            "objects": [
                {"id": "sword", "type": "item", "name": "Sword"},
            ],
            "locations": [],
            "items": [],
            "npcs": [],
            "enemies": [],
        }
        idx = object_index(quest)
        assert "sword" in idx
        assert idx["sword"]["name"] == "Sword"

    def test_merges_all_collections(self):
        quest = {
            "locations": [{"id": "loc1"}],
            "items": [{"id": "item1"}],
            "npcs": [{"id": "npc1"}],
            "enemies": [{"id": "enemy1"}],
            "objects": [{"id": "obj1"}],
        }
        idx = object_index(quest)
        for key in ("loc1", "item1", "npc1", "enemy1", "obj1"):
            assert key in idx


class TestNameAndDescription:
    def test_name_of_found(self):
        objects = {"sword": {"name": "Silver Sword"}}
        assert name_of(objects, "sword") == "Silver Sword"

    def test_name_of_missing(self):
        objects = {}
        assert name_of(objects, "missing-id") == "Missing Id"

    def test_description_of_found(self):
        objects = {"sword": {"description": "A sharp blade."}}
        assert description_of(objects, "sword") == "A sharp blade."

    def test_description_of_missing(self):
        objects = {}
        assert description_of(objects, "x") == ""


class TestFactsWith:
    def test_filters_by_predicate(self):
        state = frozenset({
            ("hero-at", "village"),
            ("has", "sword"),
            ("has", "shield"),
        })
        result = facts_with(state, "has")
        assert len(result) == 2
        assert ("has", "sword") in result
        assert ("has", "shield") in result

    def test_empty_when_no_match(self):
        state = frozenset({("hero-at", "village")})
        assert facts_with(state, "npc-at") == []


class TestStateHelpers:
    def test_current_location(self):
        state = frozenset({("hero-at", "village"), ("has", "sword")})
        assert current_location(state) == "village"

    def test_current_location_unknown(self):
        state = frozenset({("has", "sword")})
        assert current_location(state) == "unknown"

    def test_inventory(self):
        state = frozenset({("has", "sword"), ("has", "shield"), ("hero-at", "village")})
        inv = inventory(state)
        assert "sword" in inv
        assert "shield" in inv

    def test_inventory_empty(self):
        state = frozenset({("hero-at", "village")})
        assert inventory(state) == []

    def test_is_wounded_true(self):
        assert is_wounded(frozenset({("wounded",)}))

    def test_is_wounded_false(self):
        assert not is_wounded(frozenset({("hero-at", "village")}))


class TestActionLabel:
    def _action(self, name: str, args: tuple) -> GroundAction:
        return GroundAction(
            name=name,
            args=args,
            pre_pos=frozenset(),
            pre_neg=frozenset(),
            add=frozenset(),
            delete=frozenset(),
        )

    def test_travel(self):
        objects = {"village": {"name": "Village"}}
        action = self._action("travel", ("forest", "village", "s0", "s1"))
        assert action_label(action, objects) == "Go to: Village"

    def test_take(self):
        objects = {"sword": {"name": "Sword"}}
        action = self._action("take", ("sword", "village", "s0", "s1"))
        assert action_label(action, objects) == "Take: Sword"

    def test_talk(self):
        objects = {"npc1": {"name": "Elder"}}
        action = self._action("talk", ("npc1", "village", "s0", "s1"))
        assert action_label(action, objects) == "Talk to: Elder"

    def test_give(self):
        objects = {"key": {"name": "Key"}, "guard": {"name": "Guard"}}
        action = self._action("give", ("key", "guard", "village", "s0", "s1"))
        assert action_label(action, objects) == "Give Key to: Guard"

    def test_unlock(self):
        objects = {"gate1": {"name": "Gate"}, "key1": {"name": "Key"}}
        action = self._action("unlock", ("gate1", "key1", "a", "b", "s0", "s1"))
        assert action_label(action, objects) == "Unlock Gate with Key"

    def test_fight(self):
        objects = {"orc": {"name": "Orc"}, "axe": {"name": "Axe"}}
        action = self._action("fight", ("orc", "cave", "axe", "s0", "s1"))
        assert action_label(action, objects) == "Fight: Orc (Axe)"

    def test_ritual(self):
        objects = {"artifact": {"name": "Crystal"}}
        action = self._action("ritual", ("artifact", "temple", "s0", "s1"))
        assert action_label(action, objects) == "Perform ritual: Crystal"

    def test_examine_location(self):
        objects = {"village": {"name": "Village"}}
        action = self._action("examine-location", ("village",))
        assert action_label(action, objects) == "Examine: Village"

    def test_examine_npc(self):
        objects = {"npc1": {"name": "Guide"}}
        action = self._action("examine-npc", ("npc1", "village"))
        assert action_label(action, objects) == "Observe: Guide"

    def test_reveal_alternate_path(self):
        objects = {"map": {"name": "Map"}}
        action = self._action("reveal-alternate-path", ("map", "a", "b"))
        assert action_label(action, objects) == "Reveal hidden path with: Map"

    def test_travel_alternate(self):
        objects = {"secret": {"name": "Secret Path"}}
        action = self._action("travel-alternate", ("a", "secret"))
        assert action_label(action, objects) == "Take alternate path to: Secret Path"

    def test_take_optional(self):
        objects = {"potion": {"name": "Potion"}}
        action = self._action("take-optional", ("potion", "village"))
        assert action_label(action, objects) == "Take optional item: Potion"

    def test_press_npc(self):
        objects = {"thief": {"name": "Thief"}}
        action = self._action("press-npc", ("thief", "thug", "village"))
        assert action_label(action, objects) == "Press Thief for answers"

    def test_brawl(self):
        objects = {"thug": {"name": "Thug"}}
        action = self._action("brawl", ("thug", "village"))
        assert action_label(action, objects) == "Brawl with: Thug"

    def test_use_healing_item(self):
        objects = {"herb": {"name": "Herb"}}
        action = self._action("use-healing-item", ("herb",))
        assert action_label(action, objects) == "Use healing item: Herb"


class TestStepForAction:
    def _action(self, name: str, args: tuple) -> GroundAction:
        return GroundAction(
            name=name, args=args,
            pre_pos=frozenset(), pre_neg=frozenset(),
            add=frozenset(), delete=frozenset(),
        )

    def test_matches_expected_plan(self):
        quest = {
            "steps": [
                {"action": "travel", "narration": "First step."},
                {"action": "take", "narration": "Second step."},
            ],
            "expected_plan": [
                "(travel a b s0 s1)",
                "(take sword village s1 s2)",
            ],
        }
        action = self._action("travel", ("a", "b", "s0", "s1"))
        step = step_for_action(quest, action)
        assert step["narration"] == "First step."

    def test_falls_back_to_stage_index(self):
        quest = {
            "steps": [
                {"action": "talk", "narration": "Talk step."},
            ],
            "expected_plan": [],
        }
        action = self._action("talk", ("npc", "loc", "quest-s0", "quest-s1"))
        step = step_for_action(quest, action)
        assert step["narration"] == "Talk step."

    def test_returns_empty_when_no_match(self):
        quest = {"steps": [], "expected_plan": []}
        action = self._action("fight", ("orc", "cave", "sword", "s0", "s1"))
        step = step_for_action(quest, action)
        assert step == {}


class TestDialogueForAction:
    def _action(self, name: str, args: tuple) -> GroundAction:
        return GroundAction(
            name=name, args=args,
            pre_pos=frozenset(), pre_neg=frozenset(),
            add=frozenset(), delete=frozenset(),
        )

    def test_talk_dialogue(self):
        quest = {
            "npcs": [
                {
                    "id": "guide",
                    "dialogues": [
                        {"trigger": "talk", "text": "Follow me."}
                    ],
                }
            ],
        }
        action = self._action("talk", ("guide", "village", "s0", "s1"))
        assert dialogue_for_action(quest, action, {}) == "Follow me."

    def test_give_dialogue(self):
        quest = {
            "npcs": [
                {
                    "id": "guard",
                    "dialogues": [
                        {"trigger": "give:key", "text": "Thank you."}
                    ],
                }
            ],
        }
        action = self._action("give", ("key", "guard", "gate", "s0", "s1"))
        assert dialogue_for_action(quest, action, {}) == "Thank you."

    def test_no_dialogue(self):
        quest = {"npcs": []}
        action = self._action("take", ("sword", "village", "s0", "s1"))
        assert dialogue_for_action(quest, action, {}) == ""


class TestExamineText:
    def _action(self, name: str, args: tuple) -> GroundAction:
        return GroundAction(
            name=name, args=args,
            pre_pos=frozenset(), pre_neg=frozenset(),
            add=frozenset(), delete=frozenset(),
        )

    def test_examine_location(self):
        objects = {"village": {"description": "A quiet place."}}
        action = self._action("examine-location", ("village",))
        assert examine_text(action, objects) == "A quiet place."

    def test_examine_item(self):
        objects = {"sword": {"description": "Sharp and silver."}}
        action = self._action("examine-item-at", ("sword", "village"))
        assert examine_text(action, objects) == "Sharp and silver."

    def test_examine_fallback(self):
        objects = {"npc1": {"name": "Stranger"}}
        action = self._action("examine-npc", ("npc1", "village"))
        text = examine_text(action, objects)
        assert "Stranger" in text

    def test_non_examine_returns_empty(self):
        objects = {}
        action = self._action("travel", ("a", "b"))
        assert examine_text(action, objects) == ""


class TestConsequenceText:
    def _action(self, name: str, args: tuple) -> GroundAction:
        return GroundAction(
            name=name, args=args,
            pre_pos=frozenset(), pre_neg=frozenset(),
            add=frozenset(), delete=frozenset(),
        )

    def test_reveal_alternate_path(self):
        quest = {
            "consequences": {
                "hidden_routes": [
                    {"item": "map", "from": "a", "to": "b", "narration": "A secret door opens."}
                ]
            }
        }
        objects = {"map": {"name": "Map"}, "b": {"name": "Secret Room"}}
        action = self._action("reveal-alternate-path", ("map", "a", "b"))
        assert consequence_text(quest, action, objects) == "A secret door opens."

    def test_press_npc(self):
        quest = {
            "consequences": {
                "provocations": [
                    {"npc": "thief", "enemy": "thug", "location": "village", "narration": "The thief calls for help."}
                ]
            }
        }
        objects = {"thief": {"name": "Thief"}, "thug": {"name": "Thug"}}
        action = self._action("press-npc", ("thief", "thug", "village"))
        assert consequence_text(quest, action, objects) == "The thief calls for help."

    def test_brawl(self):
        objects = {"thug": {"name": "Thug"}}
        action = self._action("brawl", ("thug", "village"))
        text = consequence_text({}, action, objects)
        assert "Thug" in text
        assert "wounded" in text

    def test_use_healing_item(self):
        objects = {"herb": {"name": "Herb"}}
        action = self._action("use-healing-item", ("herb",))
        text = consequence_text({}, action, objects)
        assert "Herb" in text

    def test_travel_alternate(self):
        objects = {"secret": {"name": "Secret Path"}}
        action = self._action("travel-alternate", ("a", "secret"))
        text = consequence_text({}, action, objects)
        assert "Secret Path" in text

    def test_take_optional(self):
        objects = {"potion": {"name": "Potion", "description": "Restores health."}}
        action = self._action("take-optional", ("potion", "village"))
        text = consequence_text({}, action, objects)
        assert "Potion" in text
        assert "Restores health" in text
