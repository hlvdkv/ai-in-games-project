# Report: PDDL Quest Series Generator

## 1. Artifacts

The project contains the four required elements:

- Story generator code: `questgen/generator.py`, supported by `questgen/domain.py` and `questgen/pddl.py`.
- Quest definition folder: `quests/generated/ash_bell/`.
- Story playback code: `questgen/play.py`.
- Project report: this file.

The generated folder contains:

- `domain.pddl` - the shared world domain.
- `prompt.txt` - the original English prompt.
- `series.json` - the full generated series.
- `quest_01_quest-1.json`, `quest_02_quest-2.json`, `quest_03_quest-3.json` - quest descriptions, objects, NPCs, and dialogue.
- `quest_01_quest-1.pddl`, `quest_02_quest-2.pddl`, `quest_03_quest-3.pddl` - planning problems.
- `quest_*.plan` - plans verified by the local STRIPS solver.
- `generation_meta.json` - generation metadata.

## 2. Generation Method

The method is hybrid. A local language model creates a compact dramatic seed, while deterministic symbolic code compiles that seed into JSON and PDDL. This avoids asking the model to write raw PDDL, which is fragile. The language model contributes title, premise, motifs, quest titles, summaries, and a twist. The generator then builds a validated quest structure with locations, items, NPCs, enemies, and steps.

The first attempt used `qwen3.6:latest`, but that model was too heavy for the laptop in this setup. It repeatedly timed out and also produced long thinking output before returning useful JSON. The final run uses the much smaller `gemma3:4b` model. It completed successfully:

```json
{
  "model": "gemma3:4b",
  "used_fallback": false,
  "generation_strategy": "ollama_compact_draft_then_symbolic_pddl_compilation"
}
```

The generator still supports three modes:

- `compact` - default mode; asks the LLM for a short dramatic seed, then compiles it symbolically.
- `full` - experimental mode; asks the LLM for a full quest schema.
- `fallback` - deterministic English fallback used when the model is unavailable.

## 3. Shared PDDL Domain

The shared domain uses these types:

- `location`
- `item`
- `npc`
- `enemy`
- `gate`
- `stage`

The STRIPS actions represent the actions available in the text game:

- `travel`
- `take`
- `talk`
- `give`
- `unlock`
- `fight`
- `ritual`
- `examine-location`
- `examine-item-at`
- `examine-carried-item`
- `examine-npc`
- `examine-enemy`
- `reveal-alternate-path`
- `travel-alternate`
- `take-optional`
- `press-npc`
- `brawl`
- `use-healing-item`

Each action has preconditions and effects. The intended narrative order is represented with stage predicates such as `current-stage`, `next-stage`, `travel-step`, `take-step`, `fight-step`, and `ritual-step`. This keeps the quest as a planning problem while preventing the solver from skipping the intended story beat order. The `examine-*` actions add optional inspection choices. The consequence actions add decisions with state changes: hidden routes can be revealed, optional items can be taken, NPCs can be provoked, optional enemies can become hostile, brawls can wound the player, and healing items can remove the wound.

## 4. Repair and Verification

The generator does not trust model output directly. It normalizes IDs, filters unsupported actions, adds missing objects, and compiles quest steps into initial PDDL facts.

The repair pass can:

- add missing locations, NPCs, items, enemies, and gates,
- infer `start_location`,
- add `path` facts for movement,
- add `locked-gate` facts for locked passages,
- add `hidden-route`, `optional-item`, `healing-item`, `provocation-open`, and `optional-enemy` facts for decision consequences,
- infer carried items with `has(item)` when an item continues from a previous quest,
- add fallback dialogue for NPCs,
- compare the solver plan against the expected narrative plan.

Final verification:

```text
OK   quest_01_quest-1.pddl: 5 actions
OK   quest_02_quest-2.pddl: 7 actions
OK   quest_03_quest-3.pddl: 6 actions
```

## 5. Generated Series

Original prompt:

```text
After years away, the hero returns to their childhood village and discovers that an ancient bell beneath the mine is waking ash-born shadows. The story should feel like a dark fairy tale, but end with hope for the village.
```

Generated series title:

```text
Echoes of the Ashwood
```

LLM-generated dramatic seed:

- Motifs: `loss`, `memory`, `corruption`
- Twist: the shadows are not malevolent, but echoes of a forgotten pact made to protect the village from a far greater threat.

Quest sequence:

1. `The Silent Toll` - the call to adventure; the hero speaks with Elder Mira, finds the rusted medallion, and takes the silver knife.
2. `Beneath Blackstone` - the threshold; the hero gives the medallion to Iren the Cartographer, obtains the vein map and key, and opens the mine gate.
3. `The Bloom of Remembrance` - the ordeal and return; the hero defeats the ash guardian, listens to the bellkeeper's shade, retrieves the bell heart, and performs the rite of silence.

## 6. Playback

The text player loads both JSON and PDDL. The JSON provides descriptions, names, narration, and dialogue. The PDDL state determines which actions are currently available. The menu is generated from applicable grounded STRIPS actions, not from a hand-written script.

The first implementation was too linear: each state usually exposed only one action. The current version fixes that with optional STRIPS actions and consequence actions. For example, the first state now offers:

```text
Available actions:
  1. Talk to: Elder Mira
  2. Examine: Heatherfall
  3. Observe: Elder Mira
```

Later choices can change the game state. Examples:

```text
Available actions:
  1. Go to: Ancestor Shrine
  2. Examine: Old Well
  3. Examine carried item: Rusted Medallion
  4. Reveal hidden path with: Rusted Medallion
```

In the second quest, pressing Iren creates a hostile guard. Fighting the guard wounds the player, and using `Bruisewort Tonic` removes the wound:

```text
Pressed too hard, Iren snaps her map case shut and signals the oathbound guard.
Threats: Oathbound Guard (hostile)

You beat back Oathbound Guard, but the struggle leaves you wounded.
Status: wounded

You use Bruisewort Tonic. The wound stops bleeding.
```

Example command:

```bash
python3 -B -m questgen.play --series quests/generated/ash_bell
```

Automatic full playthrough:

```bash
python3 -B -m questgen.play --series quests/generated/ash_bell --auto
```

## 7. Strengths and Weaknesses

Strengths:

- The generated PDDL is controlled and easy to repair.
- Every quest is verified by a local STRIPS planner.
- JSON and PDDL are compiled from the same quest steps.
- The player uses the same action semantics as the planner.
- The player has optional exploration choices and consequential side choices instead of a single forced action at most states.
- `gemma3:4b` is small enough to run locally and was fast enough for this task.

Weaknesses:

- The symbolic compiler limits narrative freedom compared with full free-form LLM generation.
- Stage predicates still guide the critical quest path through a canonical narrative order.
- Cross-quest state transfer is simplified; important carried items are inferred per quest.
- Optional consequences affect local state but do not currently branch the final quest objective.
- The `full` LLM mode remains experimental and may produce invalid schemas.

## 8. Notes on Model Choice

Using English prompts improved reliability and made `gemma3:4b` sufficient. The larger `qwen3.6:latest` model was technically installed, but it was not practical here because it timed out even on compact prompts. The final generated series is therefore a real Ollama-assisted run using the smaller downloaded model, not a fallback-only result.
