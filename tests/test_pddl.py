"""Unit tests for the PDDL/STRIPS parser and planner."""

from __future__ import annotations

import pytest

from questgen.generator import build_problem_pddl
from questgen.pddl import (
    action_from_signature,
    applicable_actions,
    apply_action,
    atom_to_pddl,
    ground_actions,
    is_goal,
    load_domain,
    load_problem,
    parse_domain_text,
    parse_problem_text,
    solve,
)


class TestParseDomain:
    def test_domain_name(self, domain, domain_name):
        assert domain.name == domain_name

    def test_domain_has_actions(self, domain):
        action_names = {a.name for a in domain.actions}
        required = {
            "travel",
            "take",
            "talk",
            "give",
            "unlock",
            "fight",
            "ritual",
            "examine-location",
            "examine-item-at",
            "examine-carried-item",
            "examine-npc",
            "examine-enemy",
            "reveal-alternate-path",
            "travel-alternate",
            "take-optional",
            "press-npc",
            "brawl",
            "use-healing-item",
        }
        assert required.issubset(action_names)

    def test_travel_parameters(self, domain):
        travel = next(a for a in domain.actions if a.name == "travel")
        params = [p for p, _ in travel.parameters]
        assert params == ["?from", "?to", "?s", "?n"]

    def test_take_precondition(self, domain):
        take = next(a for a in domain.actions if a.name == "take")
        assert ("current-stage", "?s") in take.pre_pos
        assert ("take-step", "?item", "?loc", "?s", "?n") in take.pre_pos


class TestParseProblem:
    def test_parse_generated_problem(self, domain, sample_quest):
        pddl_text = build_problem_pddl(sample_quest)
        problem = parse_problem_text(pddl_text)
        assert problem.name == sample_quest["id"]
        assert problem.domain_name == domain.name
        assert problem.init
        assert problem.goal_pos

    def test_objects_by_type(self, sample_quest):
        pddl_text = build_problem_pddl(sample_quest)
        problem = parse_problem_text(pddl_text)
        assert "location" in problem.objects_by_type
        assert "stage" in problem.objects_by_type
        stage_objects = problem.objects_by_type["stage"]
        assert any(sample_quest["id"] in s for s in stage_objects)


class TestGroundActions:
    def test_ground_travel_exists(self, domain, sample_quest):
        pddl_text = build_problem_pddl(sample_quest)
        problem = parse_problem_text(pddl_text)
        grounded = ground_actions(domain, problem)
        travel_grounded = [a for a in grounded if a.name == "travel"]
        assert travel_grounded
        # Each must have 4 args
        for action in travel_grounded:
            assert len(action.args) == 4

    def test_ground_action_signature(self, domain, sample_quest):
        pddl_text = build_problem_pddl(sample_quest)
        problem = parse_problem_text(pddl_text)
        grounded = ground_actions(domain, problem)
        sigs = {a.signature() for a in grounded}
        assert all(s.startswith("(") and s.endswith(")") for s in sigs)


class TestSolve:
    def test_solve_first_quest(self, domain, sample_quest):
        pddl_text = build_problem_pddl(sample_quest)
        problem = parse_problem_text(pddl_text)
        plan = solve(domain, problem, max_depth=20)
        assert plan is not None
        assert len(plan) > 0

    def test_solve_reaches_goal(self, domain, sample_quest):
        pddl_text = build_problem_pddl(sample_quest)
        problem = parse_problem_text(pddl_text)
        plan = solve(domain, problem, max_depth=20)
        state = problem.init
        for action in plan:
            state = apply_action(state, action)
        assert is_goal(state, problem)

    def test_unsolvable_returns_none(self, domain):
        # Build a trivial unsolvable problem manually
        problem_text = """(define (problem unsolvable)
  (:domain mythic_quest)
  (:objects start - location end - location s0 s1 - stage)
  (:init
    (hero-at start)
    (current-stage s0)
    (next-stage s0 s1)
  )
  (:goal (and
    (current-stage s1)
    (hero-at end)
  ))
)"""
        problem = parse_problem_text(problem_text)
        plan = solve(domain, problem, max_depth=10)
        assert plan is None


class TestApplicableActions:
    def test_only_applicable_returned(self, domain, sample_quest):
        pddl_text = build_problem_pddl(sample_quest)
        problem = parse_problem_text(pddl_text)
        grounded = ground_actions(domain, problem)
        state = problem.init
        actions = applicable_actions(state, grounded)
        assert actions
        for action in actions:
            assert action.pre_pos.issubset(state)
            assert state.isdisjoint(action.pre_neg)


class TestApplyAction:
    def test_apply_travel_changes_location(self, domain, normalized_series):
        # Quest 2 starts with a travel step
        quest = normalized_series["quests"][1]
        pddl_text = build_problem_pddl(quest)
        problem = parse_problem_text(pddl_text)
        grounded = ground_actions(domain, problem)
        state = problem.init
        for action in applicable_actions(state, grounded):
            if action.name == "travel":
                new_state = apply_action(state, action)
                assert new_state != state
                from_loc = action.args[0]
                to_loc = action.args[1]
                assert ("hero-at", from_loc) not in new_state
                assert ("hero-at", to_loc) in new_state
                return
        pytest.fail("No applicable travel action found from init state")

    def test_apply_talk_changes_state(self, domain, sample_quest):
        # Quest 1 starts with a talk step
        pddl_text = build_problem_pddl(sample_quest)
        problem = parse_problem_text(pddl_text)
        grounded = ground_actions(domain, problem)
        state = problem.init
        for action in applicable_actions(state, grounded):
            if action.name == "talk":
                new_state = apply_action(state, action)
                assert new_state != state
                assert ("talked", action.args[0]) in new_state
                return
        pytest.fail("No applicable talk action found from init state")

    def test_apply_does_not_mutate_original(self, domain, sample_quest):
        pddl_text = build_problem_pddl(sample_quest)
        problem = parse_problem_text(pddl_text)
        grounded = ground_actions(domain, problem)
        state = problem.init
        actions = applicable_actions(state, grounded)
        original = set(state)
        apply_action(state, actions[0])
        assert set(state) == original


class TestHelpers:
    def test_action_from_signature_valid(self):
        name, args = action_from_signature("(travel start end s0 s1)")
        assert name == "travel"
        assert args == ("start", "end", "s0", "s1")

    def test_action_from_signature_invalid(self):
        with pytest.raises(ValueError):
            action_from_signature("")

    def test_atom_to_pddl(self):
        assert atom_to_pddl(("hero-at", "loc")) == "(hero-at loc)"
        assert atom_to_pddl(("current-stage", "s0")) == "(current-stage s0)"


class TestFileIO:
    def test_load_domain_from_file(self, generated_series_dir):
        domain_path = generated_series_dir / "domain.pddl"
        domain = load_domain(domain_path)
        assert domain.name == "mythic_quest"
        assert len(domain.actions) > 0

    def test_load_problem_from_file(self, generated_series_dir):
        pddl_files = list(generated_series_dir.glob("quest_*.pddl"))
        assert pddl_files
        for pddl_path in pddl_files:
            problem = load_problem(pddl_path)
            assert problem.name
            assert problem.domain_name == "mythic_quest"
            assert problem.init
            assert problem.goal_pos


class TestParseErrors:
    def test_missing_closing_paren(self):
        bad = "(define (domain test) (:requirements :strips"
        with pytest.raises(ValueError):
            parse_domain_text(bad)

    def test_unexpected_closing_paren(self):
        bad = "(define (domain test)) )"
        with pytest.raises(ValueError):
            parse_domain_text(bad)

    def test_invalid_not_expression(self):
        bad = """(define (domain bad)
  (:requirements :strips)
  (:predicates (p))
  (:action a
    :parameters ()
    :precondition (not)
    :effect ()
  )
)"""
        with pytest.raises(ValueError):
            parse_domain_text(bad)

    def test_domain_name_not_found(self):
        bad = "(define (:requirements :strips))"
        with pytest.raises(ValueError):
            parse_domain_text(bad)

    def test_problem_name_not_found(self):
        bad = "(define (:domain mythic_quest) (:init) (:goal (and)))"
        with pytest.raises(ValueError):
            parse_problem_text(bad)
