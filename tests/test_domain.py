"""Tests for the shared PDDL domain definition."""

from __future__ import annotations

import pytest

from questgen.domain import DOMAIN_NAME, DOMAIN_PDDL
from questgen.pddl import parse_domain_text


class TestDomainDefinition:
    def test_domain_name_constant(self):
        assert DOMAIN_NAME == "mythic_quest"

    def test_domain_pddl_is_non_empty(self):
        assert len(DOMAIN_PDDL) > 0
        assert "(define (domain mythic_quest)" in DOMAIN_PDDL

    def test_all_action_types_present(self, domain):
        action_names = {a.name for a in domain.actions}
        assert "travel" in action_names
        assert "take" in action_names
        assert "talk" in action_names
        assert "give" in action_names
        assert "unlock" in action_names
        assert "fight" in action_names
        assert "ritual" in action_names

    def test_optional_examine_actions_present(self, domain):
        action_names = {a.name for a in domain.actions}
        assert "examine-location" in action_names
        assert "examine-item-at" in action_names
        assert "examine-carried-item" in action_names
        assert "examine-npc" in action_names
        assert "examine-enemy" in action_names

    def test_consequence_actions_present(self, domain):
        action_names = {a.name for a in domain.actions}
        assert "reveal-alternate-path" in action_names
        assert "travel-alternate" in action_names
        assert "take-optional" in action_names
        assert "press-npc" in action_names
        assert "brawl" in action_names
        assert "use-healing-item" in action_names

    def test_ritual_removes_threat(self, domain):
        ritual = next(a for a in domain.actions if a.name == "ritual")
        assert ("not", ("threat-active",)) in [("not", atom) for atom in ritual.delete]
        # Check that threat-active is deleted
        assert ("threat-active",) in ritual.delete

    def test_fight_defeats_enemy(self, domain):
        fight = next(a for a in domain.actions if a.name == "fight")
        assert ("defeated", "?enemy") in fight.add
        assert ("hostile", "?enemy") in fight.delete

    def test_unlock_opens_path(self, domain):
        unlock = next(a for a in domain.actions if a.name == "unlock")
        assert ("path", "?from", "?to") in unlock.add
        assert ("path", "?to", "?from") in unlock.add

    def test_use_healing_item_removes_wounded(self, domain):
        heal = next(a for a in domain.actions if a.name == "use-healing-item")
        assert ("wounded",) in heal.delete
        assert ("healed-with", "?item") in heal.add

    def test_brawl_wounds_player(self, domain):
        brawl = next(a for a in domain.actions if a.name == "brawl")
        assert ("wounded",) in brawl.add
        assert ("defeated", "?enemy") in brawl.add

    def test_press_npc_makes_hostile(self, domain):
        press = next(a for a in domain.actions if a.name == "press-npc")
        assert ("hostile", "?enemy") in press.add
        assert ("angered", "?npc") in press.add
        assert ("provocation-open", "?npc", "?enemy", "?loc") in press.delete
