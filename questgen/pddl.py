"""Small PDDL/STRIPS parser and forward planner for the project domain."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
import re
from typing import Iterable


Atom = tuple[str, ...]


@dataclass(frozen=True)
class ActionSchema:
    name: str
    parameters: tuple[tuple[str, str], ...]
    pre_pos: frozenset[Atom]
    pre_neg: frozenset[Atom]
    add: frozenset[Atom]
    delete: frozenset[Atom]


@dataclass(frozen=True)
class GroundAction:
    name: str
    args: tuple[str, ...]
    pre_pos: frozenset[Atom]
    pre_neg: frozenset[Atom]
    add: frozenset[Atom]
    delete: frozenset[Atom]

    def signature(self) -> str:
        return f"({self.name} {' '.join(self.args)})"


@dataclass
class Domain:
    name: str
    actions: list[ActionSchema]


@dataclass
class Problem:
    name: str
    domain_name: str
    objects_by_type: dict[str, list[str]]
    init: frozenset[Atom]
    goal_pos: frozenset[Atom]
    goal_neg: frozenset[Atom]


def strip_comments(text: str) -> str:
    return re.sub(r";.*", "", text)


def tokenize(text: str) -> list[str]:
    return re.findall(r"\(|\)|[^\s()]+", strip_comments(text).lower())


def parse_sexp(text: str) -> list:
    tokens = tokenize(text)
    stack: list[list] = []
    root: list = []
    current = root
    for token in tokens:
        if token == "(":
            child: list = []
            current.append(child)
            stack.append(current)
            current = child
        elif token == ")":
            if not stack:
                raise ValueError("Unexpected ')' in PDDL")
            current = stack.pop()
        else:
            current.append(token)
    if stack:
        raise ValueError("Missing ')' in PDDL")
    if len(root) != 1:
        raise ValueError("PDDL file must contain exactly one top-level form")
    return root[0]


def parse_typed_symbols(parts: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    pending: list[str] = []
    index = 0
    while index < len(parts):
        token = parts[index]
        if token == "-":
            if index + 1 >= len(parts):
                raise ValueError("Typed list ended after '-'")
            type_name = parts[index + 1]
            result.extend((symbol, type_name) for symbol in pending)
            pending = []
            index += 2
        else:
            pending.append(token)
            index += 1
    result.extend((symbol, "object") for symbol in pending)
    return result


def _parse_formula(expr: list | str) -> tuple[frozenset[Atom], frozenset[Atom]]:
    pos: set[Atom] = set()
    neg: set[Atom] = set()

    def visit(node: list | str) -> None:
        if isinstance(node, str):
            raise ValueError(f"Expected predicate expression, got {node!r}")
        if not node:
            return
        head = node[0]
        if head == "and":
            for child in node[1:]:
                visit(child)
        elif head == "not":
            if len(node) != 2 or not isinstance(node[1], list):
                raise ValueError(f"Invalid not expression: {node!r}")
            neg.add(tuple(node[1]))
        else:
            pos.add(tuple(node))

    visit(expr)
    return frozenset(pos), frozenset(neg)


def parse_domain_text(text: str) -> Domain:
    form = parse_sexp(text)
    if not form or form[0] != "define":
        raise ValueError("Domain must start with (define ...)")

    domain_name = ""
    actions: list[ActionSchema] = []
    for entry in form[1:]:
        if isinstance(entry, list) and entry and entry[0] == "domain":
            domain_name = entry[1]
        if isinstance(entry, list) and entry and entry[0] == ":action":
            name = entry[1]
            parameters: tuple[tuple[str, str], ...] = ()
            pre_pos: frozenset[Atom] = frozenset()
            pre_neg: frozenset[Atom] = frozenset()
            add: frozenset[Atom] = frozenset()
            delete: frozenset[Atom] = frozenset()
            index = 2
            while index < len(entry):
                key = entry[index]
                value = entry[index + 1]
                if key == ":parameters":
                    parameters = tuple(parse_typed_symbols(value))
                elif key == ":precondition":
                    pre_pos, pre_neg = _parse_formula(value)
                elif key == ":effect":
                    add, delete = _parse_formula(value)
                index += 2
            actions.append(ActionSchema(name, parameters, pre_pos, pre_neg, add, delete))
    if not domain_name:
        raise ValueError("Domain name not found")
    return Domain(domain_name, actions)


def parse_problem_text(text: str) -> Problem:
    form = parse_sexp(text)
    if not form or form[0] != "define":
        raise ValueError("Problem must start with (define ...)")

    problem_name = ""
    domain_name = ""
    objects_by_type: dict[str, list[str]] = {}
    init: set[Atom] = set()
    goal_pos: frozenset[Atom] = frozenset()
    goal_neg: frozenset[Atom] = frozenset()

    for entry in form[1:]:
        if not isinstance(entry, list) or not entry:
            continue
        if entry[0] == "problem":
            problem_name = entry[1]
        elif entry[0] == ":domain":
            domain_name = entry[1]
        elif entry[0] == ":objects":
            for symbol, type_name in parse_typed_symbols(entry[1:]):
                objects_by_type.setdefault(type_name, []).append(symbol)
                objects_by_type.setdefault("object", []).append(symbol)
        elif entry[0] == ":init":
            init = {tuple(atom) for atom in entry[1:] if isinstance(atom, list)}
        elif entry[0] == ":goal":
            goal_pos, goal_neg = _parse_formula(entry[1])

    if not problem_name or not domain_name:
        raise ValueError("Problem name or domain name not found")
    return Problem(problem_name, domain_name, objects_by_type, frozenset(init), goal_pos, goal_neg)


def load_domain(path: str | Path) -> Domain:
    return parse_domain_text(Path(path).read_text(encoding="utf-8"))


def load_problem(path: str | Path) -> Problem:
    return parse_problem_text(Path(path).read_text(encoding="utf-8"))


def substitute(atom: Atom, binding: dict[str, str]) -> Atom:
    return tuple(binding.get(part, part) for part in atom)


def ground_actions(domain: Domain, problem: Problem) -> list[GroundAction]:
    grounded: list[GroundAction] = []
    for schema in domain.actions:
        choices: list[list[str]] = []
        missing_objects = False
        for _var, type_name in schema.parameters:
            objects = problem.objects_by_type.get(type_name, [])
            if not objects:
                missing_objects = True
                break
            choices.append(objects)
        if missing_objects:
            continue
        for args in product(*choices):
            binding = {var: value for (var, _type_name), value in zip(schema.parameters, args)}
            grounded.append(
                GroundAction(
                    schema.name,
                    tuple(args),
                    frozenset(substitute(atom, binding) for atom in schema.pre_pos),
                    frozenset(substitute(atom, binding) for atom in schema.pre_neg),
                    frozenset(substitute(atom, binding) for atom in schema.add),
                    frozenset(substitute(atom, binding) for atom in schema.delete),
                )
            )
    return grounded


def is_goal(state: frozenset[Atom], problem: Problem) -> bool:
    return problem.goal_pos.issubset(state) and state.isdisjoint(problem.goal_neg)


def applicable_actions(state: frozenset[Atom], actions: Iterable[GroundAction]) -> list[GroundAction]:
    return [
        action
        for action in actions
        if action.pre_pos.issubset(state) and state.isdisjoint(action.pre_neg)
    ]


def apply_action(state: frozenset[Atom], action: GroundAction) -> frozenset[Atom]:
    return frozenset((state - action.delete) | action.add)


def solve(domain: Domain, problem: Problem, max_depth: int = 60) -> list[GroundAction] | None:
    actions = ground_actions(domain, problem)
    start = problem.init
    if is_goal(start, problem):
        return []

    frontier: list[tuple[frozenset[Atom], list[GroundAction]]] = [(start, [])]
    visited = {start}
    while frontier:
        state, plan = frontier.pop(0)
        if len(plan) >= max_depth:
            continue
        for action in applicable_actions(state, actions):
            next_state = apply_action(state, action)
            if next_state in visited:
                continue
            next_plan = plan + [action]
            if is_goal(next_state, problem):
                return next_plan
            visited.add(next_state)
            frontier.append((next_state, next_plan))
    return None


def action_from_signature(signature: str) -> tuple[str, tuple[str, ...]]:
    parts = tokenize(signature)
    cleaned = [part for part in parts if part not in {"(", ")"}]
    if not cleaned:
        raise ValueError(f"Invalid action signature: {signature!r}")
    return cleaned[0], tuple(cleaned[1:])


def atom_to_pddl(atom: Atom) -> str:
    return f"({' '.join(atom)})"


def format_plan(plan: Iterable[GroundAction]) -> str:
    return "\n".join(action.signature() for action in plan)
