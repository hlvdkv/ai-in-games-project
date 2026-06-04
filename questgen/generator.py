"""Generate quest series with Ollama, compile them to JSON/PDDL, and verify plans."""

from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import textwrap
from typing import Any
from urllib import request

from .domain import DOMAIN_NAME, DOMAIN_PDDL
from .pddl import parse_domain_text, parse_problem_text, solve


DEFAULT_MODEL = "gemma3:4b"
DEFAULT_PROMPT = (
    "After years away, the hero returns to their childhood village and discovers "
    "that an ancient bell beneath the mine is waking ash-born shadows. The story "
    "should feel like a dark fairy tale, but end with hope for the village."
)

ACTION_ORDER = ("travel", "talk", "take", "give", "unlock", "fight", "ritual")


def slugify(value: str, fallback: str = "object") -> str:
    value = str(value or "").strip().lower()
    replacements = {
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ł": "l",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ź": "z",
        "ż": "z",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or fallback


def ollama_json(prompt: str, model: str, num_predict: int, timeout: int = 120) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "format": "json",
        "options": {"temperature": 0.65, "top_p": 0.9, "num_predict": num_predict},
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    parts: list[str] = []
    with request.urlopen(req, timeout=timeout) as response:
        for line in response:
            if not line.strip():
                continue
            chunk = json.loads(line.decode("utf-8"))
            parts.append(chunk.get("response", ""))
            if chunk.get("done"):
                break
    raw = "".join(parts)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def call_ollama(prompt: str, model: str, quests: int) -> dict[str, Any]:
    system_prompt = f"""
    You are a quest narrative generator for a university AI in games project.
    Return only valid JSON, no markdown. Use ASCII ids in kebab-case.
    Generate exactly {quests} linked quests inspired by the user premise.
    The plot should loosely follow dramatic structure and the monomyth:
    call, threshold, trials, revelation, ordeal, return.

    JSON schema:
    {{
      "series_title": "short title",
      "premise": "one paragraph",
      "quests": [
        {{
          "id": "quest-1",
          "title": "title",
          "synopsis": "short synopsis",
          "dramatic_role": "call_to_adventure|threshold|trial|ordeal|return",
          "start_location": "location-id",
          "locations": [
            {{"id":"village","name":"Village","description":"1-2 sentences"}}
          ],
          "items": [
            {{"id":"item-id","name":"Name","description":"1 sentence","location":"location-id","portable":true}}
          ],
          "npcs": [
            {{"id":"npc-id","name":"Name","description":"1 sentence","location":"location-id",
              "dialogues":[{{"trigger":"talk","text":"line"}},{{"trigger":"give:item-id","text":"line"}}]}}
          ],
          "enemies": [
            {{"id":"enemy-id","name":"Name","description":"1 sentence","location":"location-id"}}
          ],
          "steps": [
            {{"action":"travel","from":"location-id","to":"location-id","narration":"sentence"}},
            {{"action":"talk","npc":"npc-id","location":"location-id","dialogue":"spoken line","narration":"sentence"}},
            {{"action":"take","item":"item-id","location":"location-id","narration":"sentence"}},
            {{"action":"give","item":"item-id","npc":"npc-id","location":"location-id","narration":"sentence"}},
            {{"action":"unlock","gate":"gate-id","key":"item-id","from":"location-id","to":"location-id","narration":"sentence"}},
            {{"action":"fight","enemy":"enemy-id","location":"location-id","weapon":"item-id","narration":"sentence"}},
            {{"action":"ritual","artifact":"item-id","location":"location-id","narration":"sentence"}}
          ]
        }}
      ]
    }}

    Constraints:
    - Every quest must have 4 to 7 steps.
    - A take step must happen before an item is used by give, unlock, fight, or ritual.
    - A travel step must move the hero to the location required by the next interaction.
    - Include dialogues for every NPC used in talk or give.
    - Keep ids stable and lowercase.
    """
    full_prompt = "/no_think\n" + textwrap.dedent(system_prompt).strip() + "\n\nUser premise:\n" + prompt
    return ollama_json(full_prompt, model=model, num_predict=3500, timeout=120)


def call_ollama_compact(prompt: str, model: str, quests: int) -> dict[str, Any]:
    compact_prompt = f"""
    /no_think
    Return only valid compact JSON, no markdown.
    Create a dramatic seed for exactly {quests} connected fantasy quests.
    Keep the whole response short.

    Schema:
    {{
      "series_title": "title",
      "premise": "one sentence",
      "motifs": ["motif", "motif", "motif"],
      "quest_titles": ["title 1", "title 2", "title 3"],
      "quest_summaries": ["one sentence", "one sentence", "one sentence"],
      "dramatic_roles": ["call", "threshold", "ordeal_return"],
      "twist": "one sentence"
    }}

    User premise: {prompt}
    """
    return ollama_json(textwrap.dedent(compact_prompt).strip(), model=model, num_predict=700, timeout=90)


def series_from_compact_draft(draft: dict[str, Any], prompt: str, quests: int) -> dict[str, Any]:
    series = fallback_series(prompt, quests)
    if draft.get("series_title"):
        series["series_title"] = str(draft["series_title"])
    if draft.get("premise"):
        series["premise"] = str(draft["premise"])

    titles = draft.get("quest_titles") or []
    summaries = draft.get("quest_summaries") or []
    roles = draft.get("dramatic_roles") or []
    for index, quest in enumerate(series["quests"]):
        if index < len(titles) and titles[index]:
            quest["title"] = str(titles[index])
        if index < len(summaries) and summaries[index]:
            quest["synopsis"] = str(summaries[index])
        if index < len(roles) and roles[index]:
            quest["dramatic_role"] = slugify(str(roles[index]), "trial")

    motifs = draft.get("motifs") or []
    if motifs:
        series["motifs"] = [str(motif) for motif in motifs]
    if draft.get("twist"):
        series["twist"] = str(draft["twist"])
    series["llm_compact_draft"] = draft
    series["generation_strategy"] = "ollama_compact_draft_then_symbolic_pddl_compilation"
    return series


def fallback_series(prompt: str, quests: int = 3) -> dict[str, Any]:
    """Deterministic fallback used when the model response is unavailable or invalid."""
    base = {
        "series_title": "Echo of the Ashen Bell",
        "premise": prompt,
        "quests": [
            {
                "id": "quest-1",
                "title": "The Call Beneath the Old Well",
                "synopsis": "The hero returns to Heatherfall and learns that the ashen bell is waking shadows under the mine.",
                "dramatic_role": "call_to_adventure",
                "start_location": "heatherfall",
                "locations": [
                    {
                        "id": "heatherfall",
                        "name": "Heatherfall",
                        "description": "Low fog hangs over the roofs, and the villagers speak more softly than usual.",
                    },
                    {
                        "id": "old-well",
                        "name": "Old Well",
                        "description": "The stone ring of the well trembles as if someone below is striking metal.",
                    },
                    {
                        "id": "ancestor-shrine",
                        "name": "Ancestor Shrine",
                        "description": "The shrine walls carry the carved names of those who once sealed the mine.",
                    },
                    {
                        "id": "root-chapel",
                        "name": "Root Chapel",
                        "description": "A small chapel under the roots, where miners once left offerings before descending.",
                    },
                ],
                "items": [
                    {
                        "id": "rusted-medallion",
                        "name": "Rusted Medallion",
                        "description": "The mark of the first bellkeeper, cold even in a warm hand.",
                        "location": "old-well",
                        "portable": True,
                    },
                    {
                        "id": "silver-knife",
                        "name": "Silver Knife",
                        "description": "A plain blade for cutting shadows, hidden in the shrine.",
                        "location": "ancestor-shrine",
                        "portable": True,
                    },
                    {
                        "id": "healing-salve",
                        "name": "Healing Salve",
                        "description": "A miner's salve made from pale moss and ash-salt. It can close a fresh wound.",
                        "location": "root-chapel",
                        "portable": True,
                        "optional": True,
                        "healing": True,
                    },
                ],
                "npcs": [
                    {
                        "id": "elder-mira",
                        "name": "Elder Mira",
                        "description": "The last villager who remembers the night the bell fell silent.",
                        "location": "heatherfall",
                        "dialogues": [
                            {
                                "trigger": "talk",
                                "text": "If the well sings with ash, seek the bellkeeper's medallion.",
                            }
                        ],
                    }
                ],
                "enemies": [],
                "steps": [
                    {
                        "action": "talk",
                        "npc": "elder-mira",
                        "location": "heatherfall",
                        "dialogue": "If the well sings with ash, seek the bellkeeper's medallion.",
                        "narration": "Mira recognizes the hero and points toward the first wound in the earth.",
                    },
                    {
                        "action": "travel",
                        "from": "heatherfall",
                        "to": "old-well",
                        "narration": "The path to the well is overgrown with pale heather.",
                    },
                    {
                        "action": "take",
                        "item": "rusted-medallion",
                        "location": "old-well",
                        "narration": "The medallion loosens from the wet stone and falls silent in the hero's hand.",
                    },
                    {
                        "action": "travel",
                        "from": "old-well",
                        "to": "ancestor-shrine",
                        "narration": "A trail of ash leads toward the shrine.",
                    },
                    {
                        "action": "take",
                        "item": "silver-knife",
                        "location": "ancestor-shrine",
                        "narration": "The blade answers the medallion with a clean flash of light.",
                    },
                ],
                "consequences": {
                    "hidden_routes": [
                        {
                            "item": "rusted-medallion",
                            "from": "old-well",
                            "to": "root-chapel",
                            "narration": "The medallion warms in the hero's hand, and roots pull aside to reveal a narrow chapel path.",
                        }
                    ]
                },
            },
            {
                "id": "quest-2",
                "title": "The Mine Threshold",
                "synopsis": "To descend beneath the village, the hero must earn a cartographer's trust and open the sealed mine gate.",
                "dramatic_role": "threshold",
                "start_location": "ancestor-shrine",
                "locations": [
                    {
                        "id": "ancestor-shrine",
                        "name": "Ancestor Shrine",
                        "description": "Silver dust rests on the threshold like an unfinished prayer.",
                    },
                    {
                        "id": "cartographers-hut",
                        "name": "Cartographer's Hut",
                        "description": "Maps hang from the rafters, stirred by a draft from the mine.",
                    },
                    {
                        "id": "mine-gate",
                        "name": "Mine Gate",
                        "description": "Rusted bars bear the palm mark of the old bellkeeper.",
                    },
                    {
                        "id": "black-adit",
                        "name": "Black Adit",
                        "description": "The tunnel beyond the gate breathes cold air and old smoke.",
                    },
                ],
                "items": [
                    {
                        "id": "vein-map",
                        "name": "Vein Map",
                        "description": "The map shows the path toward the mine's buried heart.",
                        "location": "cartographers-hut",
                        "portable": True,
                    },
                    {
                        "id": "bellkeeper-key",
                        "name": "Bellkeeper Key",
                        "description": "A key shaped like the clapper of a small bell.",
                        "location": "mine-gate",
                        "portable": True,
                    },
                    {
                        "id": "rusted-medallion",
                        "name": "Rusted Medallion",
                        "description": "The first bellkeeper's sign, recovered from the old well.",
                        "location": "ancestor-shrine",
                        "portable": True,
                    },
                    {
                        "id": "bruisewort-tonic",
                        "name": "Bruisewort Tonic",
                        "description": "A bitter field tonic that steadies the breath and dulls pain after a fight.",
                        "location": "cartographers-hut",
                        "portable": True,
                        "optional": True,
                        "healing": True,
                    },
                ],
                "npcs": [
                    {
                        "id": "iren-cartographer",
                        "name": "Iren the Cartographer",
                        "description": "She does not trust heroes, but she trusts old signs.",
                        "location": "cartographers-hut",
                        "dialogues": [
                            {
                                "trigger": "talk",
                                "text": "Show me the bellkeeper's sign, and I will give you the true vein map.",
                            },
                            {
                                "trigger": "give:rusted-medallion",
                                "text": "That is enough. Go to the gate before the shadow learns your name.",
                            },
                        ],
                    }
                ],
                "enemies": [
                    {
                        "id": "oathbound-guard",
                        "name": "Oathbound Guard",
                        "description": "A silent guard sworn to protect Iren's maps from desperate hands.",
                        "location": "cartographers-hut",
                        "optional": True,
                        "hostile": False,
                    }
                ],
                "steps": [
                    {
                        "action": "travel",
                        "from": "ancestor-shrine",
                        "to": "cartographers-hut",
                        "narration": "The hero carries the medallion to the only person who knows the old shafts.",
                    },
                    {
                        "action": "give",
                        "item": "rusted-medallion",
                        "npc": "iren-cartographer",
                        "location": "cartographers-hut",
                        "dialogue": "That is enough. Go to the gate before the shadow learns your name.",
                        "narration": "The cartographer accepts the medallion as proof and opens a hidden map case.",
                    },
                    {
                        "action": "take",
                        "item": "vein-map",
                        "location": "cartographers-hut",
                        "narration": "The map unrolls by itself and points toward the mine gate.",
                    },
                    {
                        "action": "travel",
                        "from": "cartographers-hut",
                        "to": "mine-gate",
                        "narration": "The road to the mine threshold smells of wet iron.",
                    },
                    {
                        "action": "take",
                        "item": "bellkeeper-key",
                        "location": "mine-gate",
                        "narration": "The key waits beneath a stone marked with the map's symbol.",
                    },
                    {
                        "action": "unlock",
                        "gate": "bellkeeper-gate",
                        "key": "bellkeeper-key",
                        "from": "mine-gate",
                        "to": "black-adit",
                        "narration": "The gate opens without a creak, as if afraid to wake what waits below.",
                    },
                    {
                        "action": "travel",
                        "from": "mine-gate",
                        "to": "black-adit",
                        "narration": "The hero crosses the threshold and leaves daylight behind.",
                    },
                ],
                "consequences": {
                    "provocations": [
                        {
                            "npc": "iren-cartographer",
                            "enemy": "oathbound-guard",
                            "location": "cartographers-hut",
                            "narration": "Pressed too hard, Iren snaps her map case shut and signals the oathbound guard.",
                        }
                    ]
                },
            },
            {
                "id": "quest-3",
                "title": "The Bell's Heart",
                "synopsis": "Deep in the mine, the hero defeats an ash guardian and performs the rite of silence.",
                "dramatic_role": "ordeal_return",
                "start_location": "black-adit",
                "locations": [
                    {
                        "id": "black-adit",
                        "name": "Black Adit",
                        "description": "Ash glows inside the tunnel walls, arranging itself into old faces.",
                    },
                    {
                        "id": "bell-hall",
                        "name": "Bell Hall",
                        "description": "A vast bell hangs over a crack in the stone, though no tower was ever built here.",
                    },
                    {
                        "id": "mine-core",
                        "name": "Mine Core",
                        "description": "The deepest chamber is silent, but the silence presses against the bones.",
                    },
                    {
                        "id": "memorial-alcove",
                        "name": "Memorial Alcove",
                        "description": "Names of forgotten miners shimmer here whenever the bell heart is raised.",
                    },
                ],
                "items": [
                    {
                        "id": "silver-knife",
                        "name": "Silver Knife",
                        "description": "The shrine blade, now darker along the edge.",
                        "location": "black-adit",
                        "portable": True,
                    },
                    {
                        "id": "bell-heart",
                        "name": "Bell Heart",
                        "description": "A warm shard of metal that beats like a living heart.",
                        "location": "bell-hall",
                        "portable": True,
                    },
                    {
                        "id": "memory-charm",
                        "name": "Memory Charm",
                        "description": "A charm woven from wire and soot-black thread, warm with remembered voices.",
                        "location": "memorial-alcove",
                        "portable": True,
                        "optional": True,
                    },
                ],
                "npcs": [
                    {
                        "id": "bellkeepers-shade",
                        "name": "Bellkeeper's Shade",
                        "description": "Not an enemy, but a memory of guilt.",
                        "location": "bell-hall",
                        "dialogues": [
                            {
                                "trigger": "talk",
                                "text": "Do not break the bell. Return its heart where the earth still remembers silence.",
                            }
                        ],
                    }
                ],
                "enemies": [
                    {
                        "id": "ash-guardian",
                        "name": "Ash Guardian",
                        "description": "Armor filled with hot dust and the anger of lost miners.",
                        "location": "bell-hall",
                    }
                ],
                "steps": [
                    {
                        "action": "travel",
                        "from": "black-adit",
                        "to": "bell-hall",
                        "narration": "Each step toward the hall calls up the bell's distant toll.",
                    },
                    {
                        "action": "fight",
                        "enemy": "ash-guardian",
                        "location": "bell-hall",
                        "weapon": "silver-knife",
                        "narration": "The silver knife cuts through the dust, and the guardian collapses into ash.",
                    },
                    {
                        "action": "talk",
                        "npc": "bellkeepers-shade",
                        "location": "bell-hall",
                        "dialogue": "Do not break the bell. Return its heart where the earth still remembers silence.",
                        "narration": "The bellkeeper's shade separates grief from rage.",
                    },
                    {
                        "action": "take",
                        "item": "bell-heart",
                        "location": "bell-hall",
                        "narration": "The bell heart burns hot, but it does not harm the hero.",
                    },
                    {
                        "action": "travel",
                        "from": "bell-hall",
                        "to": "mine-core",
                        "narration": "The deepest road passes through a tunnel without echoes.",
                    },
                    {
                        "action": "ritual",
                        "artifact": "bell-heart",
                        "location": "mine-core",
                        "narration": "The rite of silence seals the crack, and for the first time in years the village hears true wind.",
                    },
                ],
                "consequences": {
                    "hidden_routes": [
                        {
                            "item": "bell-heart",
                            "from": "bell-hall",
                            "to": "memorial-alcove",
                            "narration": "The bell heart answers the names in the stone, and a memorial alcove opens behind the hanging bell.",
                        }
                    ]
                },
            },
        ],
    }
    base["quests"] = base["quests"][:quests]
    return base


def normalize_series(series: dict[str, Any], prompt: str) -> dict[str, Any]:
    series = deepcopy(series)
    series["series_title"] = series.get("series_title") or "Generated Quest Series"
    series["premise"] = series.get("premise") or prompt
    normalized_quests: list[dict[str, Any]] = []
    for quest_index, quest in enumerate(series.get("quests", []), start=1):
        quest["id"] = slugify(quest.get("id") or f"quest-{quest_index}", f"quest-{quest_index}")
        quest["title"] = quest.get("title") or f"Quest {quest_index}"
        quest["synopsis"] = quest.get("synopsis") or "Generated quest."
        quest["dramatic_role"] = quest.get("dramatic_role") or "trial"
        for collection in ("locations", "items", "npcs", "enemies"):
            quest[collection] = list(quest.get(collection) or [])
        quest["steps"] = [step for step in quest.get("steps", []) if step.get("action") in ACTION_ORDER]
        if not quest["steps"]:
            continue
        normalize_quest_ids(quest)
        repair_quest_schema(quest)
        normalized_quests.append(quest)
    if not normalized_quests:
        return fallback_series(prompt)
    series["quests"] = normalized_quests
    return series


def normalize_quest_ids(quest: dict[str, Any]) -> None:
    id_maps: dict[str, dict[str, str]] = {
        "locations": {},
        "items": {},
        "npcs": {},
        "enemies": {},
    }
    for collection in id_maps:
        for index, obj in enumerate(quest.get(collection, []), start=1):
            old_id = str(obj.get("id") or obj.get("name") or f"{collection[:-1]}-{index}")
            new_id = slugify(old_id, f"{collection[:-1]}-{index}")
            obj["id"] = new_id
            id_maps[collection][old_id] = new_id

    def map_value(kind: str, value: str | None, fallback: str) -> str:
        if value is None:
            return fallback
        return id_maps[kind].get(str(value), slugify(str(value), fallback))

    for item in quest.get("items", []):
        if item.get("location"):
            item["location"] = map_value("locations", item.get("location"), "location")
    for npc in quest.get("npcs", []):
        if npc.get("location"):
            npc["location"] = map_value("locations", npc.get("location"), "location")
    for enemy in quest.get("enemies", []):
        if enemy.get("location"):
            enemy["location"] = map_value("locations", enemy.get("location"), "location")

    for step in quest.get("steps", []):
        action = step.get("action")
        if action == "travel":
            step["from"] = map_value("locations", step.get("from"), "location")
            step["to"] = map_value("locations", step.get("to"), "location")
        elif action == "take":
            step["item"] = map_value("items", step.get("item"), "item")
            step["location"] = map_value("locations", step.get("location"), "location")
        elif action == "talk":
            step["npc"] = map_value("npcs", step.get("npc"), "npc")
            step["location"] = map_value("locations", step.get("location"), "location")
        elif action == "give":
            step["item"] = map_value("items", step.get("item"), "item")
            step["npc"] = map_value("npcs", step.get("npc"), "npc")
            step["location"] = map_value("locations", step.get("location"), "location")
        elif action == "unlock":
            step["gate"] = slugify(step.get("gate") or "gate", "gate")
            step["key"] = map_value("items", step.get("key"), "item")
            step["from"] = map_value("locations", step.get("from"), "location")
            step["to"] = map_value("locations", step.get("to"), "location")
        elif action == "fight":
            step["enemy"] = map_value("enemies", step.get("enemy"), "enemy")
            step["location"] = map_value("locations", step.get("location"), "location")
            step["weapon"] = map_value("items", step.get("weapon"), "item")
        elif action == "ritual":
            step["artifact"] = map_value("items", step.get("artifact"), "item")
            step["location"] = map_value("locations", step.get("location"), "location")

    consequences = quest.get("consequences", {})
    for route in consequences.get("hidden_routes", []):
        route["item"] = map_value("items", route.get("item"), "item")
        route["from"] = map_value("locations", route.get("from"), "location")
        route["to"] = map_value("locations", route.get("to"), "location")
    for provocation in consequences.get("provocations", []):
        provocation["npc"] = map_value("npcs", provocation.get("npc"), "npc")
        provocation["enemy"] = map_value("enemies", provocation.get("enemy"), "enemy")
        provocation["location"] = map_value("locations", provocation.get("location"), "location")

    if quest.get("start_location"):
        quest["start_location"] = map_value("locations", quest.get("start_location"), "location")


def ensure_object(collection: list[dict[str, Any]], object_id: str, **defaults: Any) -> dict[str, Any]:
    for obj in collection:
        if obj.get("id") == object_id:
            for key, value in defaults.items():
                obj.setdefault(key, value)
            return obj
    obj = {"id": object_id, **defaults}
    collection.append(obj)
    return obj


def repair_quest_schema(quest: dict[str, Any]) -> list[str]:
    repairs: list[str] = []
    locations = quest.setdefault("locations", [])
    items = quest.setdefault("items", [])
    npcs = quest.setdefault("npcs", [])
    enemies = quest.setdefault("enemies", [])

    def location_name(location_id: str) -> str:
        return location_id.replace("-", " ").title()

    for step in quest.get("steps", []):
        action = step.get("action")
        touched_locations: list[str] = []
        if action == "travel":
            touched_locations = [step["from"], step["to"]]
        elif action in {"take", "talk", "give", "fight", "ritual"}:
            touched_locations = [step["location"]]
        elif action == "unlock":
            touched_locations = [step["from"], step["to"]]
        for location_id in touched_locations:
            if not any(loc.get("id") == location_id for loc in locations):
                repairs.append(f"added missing location {location_id}")
                ensure_object(
                    locations,
                    location_id,
                    name=location_name(location_id),
                    description=f"A location important to the quest: {location_name(location_id)}.",
                )

        if action == "take":
            ensure_object(
                items,
                step["item"],
                name=step["item"].replace("-", " ").title(),
                description="An item needed for the next part of the quest.",
                location=step["location"],
                portable=True,
            )
        elif action == "give":
            ensure_object(
                items,
                step["item"],
                name=step["item"].replace("-", " ").title(),
                description="An item meant to be given to a character.",
                location=quest.get("start_location") or step["location"],
                portable=True,
            )
            npc = ensure_object(
                npcs,
                step["npc"],
                name=step["npc"].replace("-", " ").title(),
                description="A character connected to the quest.",
                location=step["location"],
                dialogues=[],
            )
            trigger = f"give:{step['item']}"
            if not any(dialogue.get("trigger") == trigger for dialogue in npc.setdefault("dialogues", [])):
                npc["dialogues"].append(
                    {"trigger": trigger, "text": step.get("dialogue") or "Thank you. The path is clearer now."}
                )
        elif action == "talk":
            npc = ensure_object(
                npcs,
                step["npc"],
                name=step["npc"].replace("-", " ").title(),
                description="A speaker who gives the player a story lead.",
                location=step["location"],
                dialogues=[],
            )
            if not any(dialogue.get("trigger") == "talk" for dialogue in npc.setdefault("dialogues", [])):
                npc["dialogues"].append({"trigger": "talk", "text": step.get("dialogue") or "Listen carefully."})
        elif action == "unlock":
            ensure_object(
                items,
                step["key"],
                name=step["key"].replace("-", " ").title(),
                description="A key that opens the passage.",
                location=step["from"],
                portable=True,
            )
        elif action == "fight":
            ensure_object(
                enemies,
                step["enemy"],
                name=step["enemy"].replace("-", " ").title(),
                description="Wrog stojacy na drodze bohatera.",
                location=step["location"],
            )
            ensure_object(
                items,
                step["weapon"],
                name=step["weapon"].replace("-", " ").title(),
                description="A weapon needed in combat.",
                location=quest.get("start_location") or step["location"],
                portable=True,
            )
        elif action == "ritual":
            ensure_object(
                items,
                step["artifact"],
                name=step["artifact"].replace("-", " ").title(),
                description="An artifact needed for the ritual.",
                location=step["location"],
                portable=True,
            )

    consequences = quest.get("consequences", {})
    for route in consequences.get("hidden_routes", []):
        for location_id in (route["from"], route["to"]):
            if not any(loc.get("id") == location_id for loc in locations):
                repairs.append(f"added consequence location {location_id}")
                ensure_object(
                    locations,
                    location_id,
                    name=location_name(location_id),
                    description=f"A location revealed by a consequence: {location_name(location_id)}.",
                )
        ensure_object(
            items,
            route["item"],
            name=route["item"].replace("-", " ").title(),
            description="An item that can reveal an alternate path.",
            location=route["from"],
            portable=True,
        )

    for provocation in consequences.get("provocations", []):
        ensure_object(
            npcs,
            provocation["npc"],
            name=provocation["npc"].replace("-", " ").title(),
            description="A character who can be provoked by an aggressive choice.",
            location=provocation["location"],
            dialogues=[],
        )
        ensure_object(
            enemies,
            provocation["enemy"],
            name=provocation["enemy"].replace("-", " ").title(),
            description="An enemy drawn into the quest by a risky choice.",
            location=provocation["location"],
            optional=True,
            hostile=False,
        )

    if not quest.get("start_location"):
        first = quest["steps"][0]
        if first["action"] == "travel":
            quest["start_location"] = first["from"]
        else:
            quest["start_location"] = first.get("location")
        repairs.append("inferred missing start_location")

    return repairs


def build_objects(quest: dict[str, Any]) -> dict[str, set[str]]:
    objects: dict[str, set[str]] = defaultdict(set)
    for location in quest.get("locations", []):
        objects["location"].add(location["id"])
    for item in quest.get("items", []):
        objects["item"].add(item["id"])
    for npc in quest.get("npcs", []):
        objects["npc"].add(npc["id"])
    for enemy in quest.get("enemies", []):
        objects["enemy"].add(enemy["id"])
    for step in quest.get("steps", []):
        if step["action"] == "unlock":
            objects["gate"].add(step["gate"])
    for index in range(len(quest.get("steps", [])) + 1):
        objects["stage"].add(f"{quest['id']}-s{index}")
    return objects


def build_init_facts(quest: dict[str, Any]) -> set[tuple[str, ...]]:
    facts: set[tuple[str, ...]] = {("threat-active",)}
    steps = quest["steps"]
    facts.add(("hero-at", quest["start_location"]))
    facts.add(("visited", quest["start_location"]))
    facts.add(("current-stage", f"{quest['id']}-s0"))

    for location in quest.get("locations", []):
        facts.add(("unexamined-location", location["id"]))

    consequences = quest.get("consequences", {})
    for route in consequences.get("hidden_routes", []):
        facts.add(("hidden-route", route["item"], route["from"], route["to"]))
    for provocation in consequences.get("provocations", []):
        facts.add(
            (
                "provocation-open",
                provocation["npc"],
                provocation["enemy"],
                provocation["location"],
            )
        )

    for index in range(len(steps)):
        current = f"{quest['id']}-s{index}"
        next_stage = f"{quest['id']}-s{index + 1}"
        facts.add(("next-stage", current, next_stage))

    locked_edges = {
        (step["from"], step["to"])
        for step in steps
        if step.get("action") == "unlock"
    }
    for index, step in enumerate(steps):
        current = f"{quest['id']}-s{index}"
        next_stage = f"{quest['id']}-s{index + 1}"
        action = step["action"]
        if action == "travel":
            facts.add(("travel-step", step["from"], step["to"], current, next_stage))
            if (step["from"], step["to"]) not in locked_edges:
                facts.add(("path", step["from"], step["to"]))
                facts.add(("path", step["to"], step["from"]))
        elif action == "take":
            facts.add(("take-step", step["item"], step["location"], current, next_stage))
        elif action == "talk":
            facts.add(("talk-step", step["npc"], step["location"], current, next_stage))
        elif action == "give":
            facts.add(("give-step", step["item"], step["npc"], step["location"], current, next_stage))
            facts.add(("wants", step["npc"], step["item"]))
        elif action == "unlock":
            facts.add(("unlock-step", step["gate"], step["key"], step["from"], step["to"], current, next_stage))
            facts.add(("locked-gate", step["gate"], step["from"], step["to"]))
        elif action == "fight":
            facts.add(("fight-step", step["enemy"], step["location"], step["weapon"], current, next_stage))
        elif action == "ritual":
            facts.add(("ritual-step", step["artifact"], step["location"], current, next_stage))
            facts.add(("ritual-site", step["location"]))

    taken_items = {step["item"] for step in steps if step["action"] == "take"}
    used_items = set()
    for step in steps:
        if step["action"] == "give":
            used_items.add(step["item"])
        elif step["action"] == "unlock":
            used_items.add(step["key"])
        elif step["action"] == "fight":
            used_items.add(step["weapon"])
        elif step["action"] == "ritual":
            used_items.add(step["artifact"])

    for item in quest.get("items", []):
        item_id = item["id"]
        facts.add(("portable", item_id))
        facts.add(("unexamined-item", item_id))
        if item.get("optional"):
            facts.add(("optional-item", item_id))
        if item.get("healing"):
            facts.add(("healing-item", item_id))
        if item.get("portable", True):
            facts.add(("portable", item_id))
        if item_id in used_items and item_id not in taken_items:
            facts.add(("has", item_id))
        else:
            location = item.get("location") or quest["start_location"]
            facts.add(("item-at", item_id, location))
        if any(step.get("weapon") == item_id for step in steps if step["action"] == "fight"):
            facts.add(("weapon", item_id))

    for npc in quest.get("npcs", []):
        location = npc.get("location") or quest["start_location"]
        facts.add(("npc-at", npc["id"], location))
        facts.add(("can-talk", npc["id"]))
        facts.add(("unexamined-npc", npc["id"]))

    for enemy in quest.get("enemies", []):
        location = enemy.get("location") or quest["start_location"]
        facts.add(("enemy-at", enemy["id"], location))
        if enemy.get("hostile", True):
            facts.add(("hostile", enemy["id"]))
        if enemy.get("optional"):
            facts.add(("optional-enemy", enemy["id"]))
        facts.add(("unexamined-enemy", enemy["id"]))

    return facts


def pddl_typed_objects(objects: dict[str, set[str]]) -> str:
    lines = []
    for type_name in ("location", "item", "npc", "enemy", "gate", "stage"):
        values = sorted(objects.get(type_name, set()))
        if values:
            lines.append(f"    {' '.join(values)} - {type_name}")
    return "\n".join(lines)


def atom_to_pddl(atom: tuple[str, ...]) -> str:
    return f"({' '.join(atom)})"


def build_problem_pddl(quest: dict[str, Any]) -> str:
    objects = build_objects(quest)
    init_facts = build_init_facts(quest)
    final_stage = f"{quest['id']}-s{len(quest['steps'])}"
    init = "\n".join(f"    {atom_to_pddl(atom)}" for atom in sorted(init_facts))
    return f"""(define (problem {quest['id']})
  (:domain {DOMAIN_NAME})
  (:objects
{pddl_typed_objects(objects)}
  )
  (:init
{init}
  )
  (:goal (and
    (current-stage {final_stage})
  ))
)
"""


def expected_plan(quest: dict[str, Any]) -> list[str]:
    signatures: list[str] = []
    for index, step in enumerate(quest["steps"]):
        current = f"{quest['id']}-s{index}"
        next_stage = f"{quest['id']}-s{index + 1}"
        action = step["action"]
        if action == "travel":
            args = [step["from"], step["to"], current, next_stage]
        elif action == "take":
            args = [step["item"], step["location"], current, next_stage]
        elif action == "talk":
            args = [step["npc"], step["location"], current, next_stage]
        elif action == "give":
            args = [step["item"], step["npc"], step["location"], current, next_stage]
        elif action == "unlock":
            args = [step["gate"], step["key"], step["from"], step["to"], current, next_stage]
        elif action == "fight":
            args = [step["enemy"], step["location"], step["weapon"], current, next_stage]
        elif action == "ritual":
            args = [step["artifact"], step["location"], current, next_stage]
        else:
            continue
        signatures.append(f"({action} {' '.join(args)})")
    return signatures


def enrich_quest_json(quest: dict[str, Any], plan: list[str], repairs: list[str]) -> dict[str, Any]:
    objects: list[dict[str, Any]] = []
    for type_name, collection in (
        ("location", "locations"),
        ("item", "items"),
        ("npc", "npcs"),
        ("enemy", "enemies"),
    ):
        for obj in quest.get(collection, []):
            entry = {
                "id": obj["id"],
                "type": type_name,
                "name": obj.get("name", obj["id"]),
                "description": obj.get("description", ""),
            }
            if obj.get("dialogues"):
                entry["dialogues"] = obj["dialogues"]
            objects.append(entry)
    for step in quest.get("steps", []):
        if step["action"] == "unlock":
            objects.append(
                {
                    "id": step["gate"],
                    "type": "gate",
                    "name": step["gate"].replace("-", " ").title(),
                    "description": "A locked passage controlled by the locked-gate predicate.",
                }
            )
    quest["objects"] = objects
    quest["expected_plan"] = expected_plan(quest)
    quest["verified_plan"] = plan
    quest["repairs"] = repairs
    return quest


def compile_and_verify(series: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str], dict[str, str], dict[str, list[str]]]:
    domain = parse_domain_text(DOMAIN_PDDL)
    quest_json: dict[str, str] = {}
    quest_pddl: dict[str, str] = {}
    plans: dict[str, list[str]] = {}

    for quest in series["quests"]:
        repairs = repair_quest_schema(quest)
        problem_pddl = build_problem_pddl(quest)
        problem = parse_problem_text(problem_pddl)
        plan = solve(domain, problem, max_depth=max(20, len(quest["steps"]) + 5))
        if plan is None:
            repairs.append("first planning attempt failed; rebuilt inferred facts")
            repair_quest_schema(quest)
            problem_pddl = build_problem_pddl(quest)
            problem = parse_problem_text(problem_pddl)
            plan = solve(domain, problem, max_depth=max(20, len(quest["steps"]) + 5))
        if plan is None:
            raise RuntimeError(f"Quest {quest['id']} is not solvable after repair")

        plan_signatures = [action.signature() for action in plan]
        intended = expected_plan(quest)
        if plan_signatures != intended:
            repairs.append("planner found a valid but different plan; stage predicates kept as canonical order")
        enrich_quest_json(quest, plan_signatures, repairs)
        quest_pddl[quest["id"]] = problem_pddl
        quest_json[quest["id"]] = json.dumps(quest, ensure_ascii=False, indent=2)
        plans[quest["id"]] = plan_signatures

    return series, quest_json, quest_pddl, plans


def write_series(
    series: dict[str, Any],
    quest_json: dict[str, str],
    quest_pddl: dict[str, str],
    plans: dict[str, list[str]],
    prompt: str,
    model: str,
    out_dir: Path,
    used_fallback: bool,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "domain.pddl").write_text(DOMAIN_PDDL, encoding="utf-8")
    (out_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    (out_dir / "series.json").write_text(json.dumps(series, ensure_ascii=False, indent=2), encoding="utf-8")

    for index, quest in enumerate(series["quests"], start=1):
        prefix = f"quest_{index:02d}_{quest['id']}"
        (out_dir / f"{prefix}.json").write_text(quest_json[quest["id"]], encoding="utf-8")
        (out_dir / f"{prefix}.pddl").write_text(quest_pddl[quest["id"]], encoding="utf-8")
        (out_dir / f"{prefix}.plan").write_text("\n".join(plans[quest["id"]]) + "\n", encoding="utf-8")

    metadata = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "used_fallback": used_fallback,
        "generation_strategy": series.get("generation_strategy", "full_llm_schema_then_symbolic_pddl_compilation"),
        "generation_warnings": series.get("generation_warnings", []),
        "domain": DOMAIN_NAME,
        "quest_count": len(series["quests"]),
        "files": sorted(path.name for path in out_dir.iterdir() if path.is_file()),
    }
    (out_dir / "generation_meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def generate(prompt: str, model: str, quests: int, out_dir: Path, mode: str = "compact") -> dict[str, Any]:
    used_fallback = False
    try:
        if mode == "fallback":
            used_fallback = True
            series = normalize_series(fallback_series(prompt, quests), prompt)
            series["generation_strategy"] = "fallback_template_then_symbolic_pddl_compilation"
        elif mode == "full":
            raw = call_ollama(prompt, model, quests)
            series = normalize_series(raw, prompt)
            series["generation_strategy"] = "full_llm_schema_then_symbolic_pddl_compilation"
        else:
            raw = call_ollama_compact(prompt, model, quests)
            series = normalize_series(series_from_compact_draft(raw, prompt, quests), prompt)
    except Exception as exc:
        used_fallback = True
        series = normalize_series(fallback_series(prompt, quests), prompt)
        series.setdefault("generation_warnings", []).append(f"Ollama generation failed: {exc}")
        series["generation_strategy"] = "fallback_template_then_symbolic_pddl_compilation"

    try:
        series, quest_json, quest_pddl, plans = compile_and_verify(series)
    except Exception as exc:
        used_fallback = True
        series = normalize_series(fallback_series(prompt, quests), prompt)
        series.setdefault("generation_warnings", []).append(f"Generated draft rejected by planner: {exc}")
        series["generation_strategy"] = "fallback_template_after_planner_rejection"
        series, quest_json, quest_pddl, plans = compile_and_verify(series)

    write_series(series, quest_json, quest_pddl, plans, prompt, model, out_dir, used_fallback)
    return {
        "out_dir": str(out_dir),
        "used_fallback": used_fallback,
        "quests": [quest["id"] for quest in series["quests"]],
        "plans": plans,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and verify a PDDL quest series.")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Short story premise.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name.")
    parser.add_argument("--quests", type=int, default=3, help="Number of quests to request.")
    parser.add_argument(
        "--out",
        default="quests/generated/ash_bell",
        help="Output directory for domain, quest JSON/PDDL, plans, and metadata.",
    )
    parser.add_argument(
        "--mode",
        choices=("compact", "full", "fallback"),
        default="compact",
        help="Use compact LLM seed by default, or ask the model for the full schema.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    result = generate(args.prompt, args.model, args.quests, Path(args.out), mode=args.mode)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
