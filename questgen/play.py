"""Text interface for playing generated PDDL/JSON quest series."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .pddl import (
    GroundAction,
    applicable_actions,
    apply_action,
    ground_actions,
    is_goal,
    load_domain,
    load_problem,
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def find_quest_pairs(series_dir: Path) -> list[tuple[Path, Path]]:
    json_files = sorted(path for path in series_dir.glob("quest_*.json") if path.is_file())
    pairs: list[tuple[Path, Path]] = []
    for json_path in json_files:
        pddl_path = json_path.with_suffix(".pddl")
        if pddl_path.exists():
            pairs.append((json_path, pddl_path))
    return pairs


def object_index(quest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for collection in ("locations", "items", "npcs", "enemies", "objects"):
        for obj in quest.get(collection, []):
            index[obj["id"]] = obj
    return index


def name_of(objects: dict[str, dict[str, Any]], object_id: str) -> str:
    return objects.get(object_id, {}).get("name", object_id.replace("-", " ").title())


def description_of(objects: dict[str, dict[str, Any]], object_id: str) -> str:
    return objects.get(object_id, {}).get("description", "")


def facts_with(state: frozenset[tuple[str, ...]], predicate: str) -> list[tuple[str, ...]]:
    return sorted(atom for atom in state if atom and atom[0] == predicate)


def current_location(state: frozenset[tuple[str, ...]]) -> str:
    for atom in state:
        if atom[0] == "hero-at":
            return atom[1]
    return "unknown"


def inventory(state: frozenset[tuple[str, ...]]) -> list[str]:
    return sorted(atom[1] for atom in state if atom[0] == "has")


def is_wounded(state: frozenset[tuple[str, ...]]) -> bool:
    return ("wounded",) in state


def signature(action: GroundAction) -> str:
    return action.signature()


def stage_index_from_action(action: GroundAction) -> int | None:
    if len(action.args) < 2:
        return None
    stage = action.args[-2]
    if "-s" not in stage:
        return None
    try:
        return int(stage.rsplit("-s", 1)[1])
    except ValueError:
        return None


def step_for_action(quest: dict[str, Any], action: GroundAction) -> dict[str, Any]:
    expected = quest.get("expected_plan", [])
    sig = signature(action)
    if sig in expected:
        return quest.get("steps", [])[expected.index(sig)]
    index = stage_index_from_action(action)
    if index is not None and index < len(quest.get("steps", [])):
        return quest["steps"][index]
    return {}


def action_label(action: GroundAction, objects: dict[str, dict[str, Any]]) -> str:
    args = action.args
    if action.name == "travel":
        return f"Go to: {name_of(objects, args[1])}"
    if action.name == "take":
        return f"Take: {name_of(objects, args[0])}"
    if action.name == "talk":
        return f"Talk to: {name_of(objects, args[0])}"
    if action.name == "give":
        return f"Give {name_of(objects, args[0])} to: {name_of(objects, args[1])}"
    if action.name == "unlock":
        return f"Unlock {name_of(objects, args[0])} with {name_of(objects, args[1])}"
    if action.name == "fight":
        return f"Fight: {name_of(objects, args[0])} ({name_of(objects, args[2])})"
    if action.name == "ritual":
        return f"Perform ritual: {name_of(objects, args[0])}"
    if action.name == "examine-location":
        return f"Examine: {name_of(objects, args[0])}"
    if action.name == "examine-item-at":
        return f"Examine item: {name_of(objects, args[0])}"
    if action.name == "examine-carried-item":
        return f"Examine carried item: {name_of(objects, args[0])}"
    if action.name == "examine-npc":
        return f"Observe: {name_of(objects, args[0])}"
    if action.name == "examine-enemy":
        return f"Study enemy: {name_of(objects, args[0])}"
    if action.name == "reveal-alternate-path":
        return f"Reveal hidden path with: {name_of(objects, args[0])}"
    if action.name == "travel-alternate":
        return f"Take alternate path to: {name_of(objects, args[1])}"
    if action.name == "take-optional":
        return f"Take optional item: {name_of(objects, args[0])}"
    if action.name == "press-npc":
        return f"Press {name_of(objects, args[0])} for answers"
    if action.name == "brawl":
        return f"Brawl with: {name_of(objects, args[0])}"
    if action.name == "use-healing-item":
        return f"Use healing item: {name_of(objects, args[0])}"
    return signature(action)


def examine_text(action: GroundAction, objects: dict[str, dict[str, Any]]) -> str:
    if action.name == "examine-location":
        object_id = action.args[0]
    elif action.name in {"examine-item-at", "examine-carried-item", "examine-npc", "examine-enemy"}:
        object_id = action.args[0]
    else:
        return ""

    description = description_of(objects, object_id)
    if description:
        return description
    return f"You take a closer look at {name_of(objects, object_id)}."


def consequence_text(quest: dict[str, Any], action: GroundAction, objects: dict[str, dict[str, Any]]) -> str:
    consequences = quest.get("consequences", {})
    if action.name == "reveal-alternate-path":
        item_id, from_id, to_id = action.args
        for route in consequences.get("hidden_routes", []):
            if route.get("item") == item_id and route.get("from") == from_id and route.get("to") == to_id:
                return route.get("narration", "")
        return f"{name_of(objects, item_id)} reveals a hidden way to {name_of(objects, to_id)}."
    if action.name == "travel-alternate":
        return f"You leave the main route and slip toward {name_of(objects, action.args[1])}."
    if action.name == "take-optional":
        item_id = action.args[0]
        description = description_of(objects, item_id)
        if description:
            return f"You take {name_of(objects, item_id)}. {description}"
        return f"You take {name_of(objects, item_id)}."
    if action.name == "press-npc":
        npc_id, enemy_id, loc_id = action.args
        for provocation in consequences.get("provocations", []):
            if (
                provocation.get("npc") == npc_id
                and provocation.get("enemy") == enemy_id
                and provocation.get("location") == loc_id
            ):
                return provocation.get("narration", "")
        return f"{name_of(objects, npc_id)} loses patience, and {name_of(objects, enemy_id)} steps forward."
    if action.name == "brawl":
        return f"You beat back {name_of(objects, action.args[0])}, but the struggle leaves you wounded."
    if action.name == "use-healing-item":
        return f"You use {name_of(objects, action.args[0])}. The wound stops bleeding."
    return ""


def dialogue_for_action(quest: dict[str, Any], action: GroundAction, step: dict[str, Any]) -> str:
    if action.name == "talk":
        if step.get("dialogue"):
            return step["dialogue"]
        npc_id = action.args[0]
        for npc in quest.get("npcs", []):
            if npc.get("id") == npc_id:
                for dialogue in npc.get("dialogues", []):
                    if dialogue.get("trigger") == "talk":
                        return dialogue.get("text", "")
    if action.name == "give":
        npc_id = action.args[1]
        item_id = action.args[0]
        trigger = f"give:{item_id}"
        for npc in quest.get("npcs", []):
            if npc.get("id") == npc_id:
                for dialogue in npc.get("dialogues", []):
                    if dialogue.get("trigger") == trigger:
                        return dialogue.get("text", "")
    return ""


def print_location(state: frozenset[tuple[str, ...]], quest: dict[str, Any], objects: dict[str, dict[str, Any]]) -> None:
    loc = current_location(state)
    print(f"\n== {name_of(objects, loc)} ==")
    description = description_of(objects, loc)
    if description:
        print(description)

    visible_items = [atom[1] for atom in facts_with(state, "item-at") if atom[2] == loc]
    visible_npcs = [atom[1] for atom in facts_with(state, "npc-at") if atom[2] == loc]
    visible_enemies = [atom[1] for atom in facts_with(state, "enemy-at") if atom[2] == loc]

    if visible_items:
        print("Items: " + ", ".join(name_of(objects, item) for item in visible_items))
    if visible_npcs:
        print("Characters: " + ", ".join(name_of(objects, npc) for npc in visible_npcs))
    if visible_enemies:
        enemy_names = []
        for enemy in visible_enemies:
            suffix = " (hostile)" if ("hostile", enemy) in state else ""
            enemy_names.append(name_of(objects, enemy) + suffix)
        print("Threats: " + ", ".join(enemy_names))

    inv = inventory(state)
    print("Inventory: " + (", ".join(name_of(objects, item) for item in inv) if inv else "empty"))
    if is_wounded(state):
        print("Status: wounded")


def play_quest(domain_path: Path, quest_json_path: Path, quest_pddl_path: Path, auto: bool = False) -> None:
    domain = load_domain(domain_path)
    problem = load_problem(quest_pddl_path)
    quest = load_json(quest_json_path)
    objects = object_index(quest)
    all_actions = ground_actions(domain, problem)
    state = problem.init

    print(f"\n# {quest.get('title', problem.name)}")
    if quest.get("synopsis"):
        print(quest["synopsis"])

    while not is_goal(state, problem):
        print_location(state, quest, objects)
        options = applicable_actions(state, all_actions)
        if not options:
            print("\nNo available actions. The quest is stuck before reaching its goal.")
            return

        print("\nAvailable actions:")
        for index, action in enumerate(options, start=1):
            print(f"  {index}. {action_label(action, objects)}")

        if auto:
            choice_index = 0
            print(f"> {choice_index + 1}")
        else:
            raw = input("> ").strip().lower()
            if raw in {"q", "quit", "exit"}:
                raise KeyboardInterrupt
            if raw in {"look", "l"}:
                continue
            if raw in {"inv", "i"}:
                print("Inventory: " + ", ".join(name_of(objects, item) for item in inventory(state)))
                continue
            try:
                choice_index = int(raw) - 1
            except ValueError:
                print("Enter an action number, 'look', 'inv', or 'q'.")
                continue
            if choice_index < 0 or choice_index >= len(options):
                print("That action is not available.")
                continue

        action = options[choice_index]
        step = step_for_action(quest, action)
        state = apply_action(state, action)
        narration = step.get("narration")
        if action.name.startswith("examine-"):
            print("\n" + examine_text(action, objects))
        elif action.name in {
            "reveal-alternate-path",
            "travel-alternate",
            "take-optional",
            "press-npc",
            "brawl",
            "use-healing-item",
        }:
            print("\n" + consequence_text(quest, action, objects))
        elif narration:
            print("\n" + narration)
        dialogue = dialogue_for_action(quest, action, step)
        if dialogue:
            speaker = ""
            if action.name == "talk":
                speaker = name_of(objects, action.args[0])
            elif action.name == "give":
                speaker = name_of(objects, action.args[1])
            print(f"{speaker}: \"{dialogue}\"")

    print(f"\nQuest completed: {quest.get('title', problem.name)}")


def play_series(series_dir: Path, auto: bool = False, only_quest: int | None = None) -> None:
    domain_path = series_dir / "domain.pddl"
    if not domain_path.exists():
        raise FileNotFoundError(f"Missing domain file: {domain_path}")
    pairs = find_quest_pairs(series_dir)
    if not pairs:
        raise FileNotFoundError(f"No quest_*.json/.pddl pairs found in {series_dir}")
    if only_quest is not None:
        pairs = [pairs[only_quest - 1]]

    series_path = series_dir / "series.json"
    if series_path.exists():
        series = load_json(series_path)
        print(f"Series: {series.get('series_title', series_dir.name)}")
        if series.get("premise"):
            print(series["premise"])

    for json_path, pddl_path in pairs:
        play_quest(domain_path, json_path, pddl_path, auto=auto)

    print("\nSeries completed.")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Play a generated quest series in a text interface.")
    parser.add_argument("--series", default="quests/generated/ash_bell", help="Directory with generated quest files.")
    parser.add_argument("--auto", action="store_true", help="Automatically choose the first applicable action.")
    parser.add_argument("--quest", type=int, help="Play only one quest by 1-based index.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        play_series(Path(args.series), auto=args.auto, only_quest=args.quest)
    except KeyboardInterrupt:
        print("\nGame interrupted.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
