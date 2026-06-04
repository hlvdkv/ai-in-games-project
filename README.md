# PDDL Quest Generator

This project contains a hybrid quest generator, a shared STRIPS/PDDL domain, a generated quest series, and a text-based player.

## Structure

- `questgen/generator.py` - story generator, Ollama integration, JSON/PDDL compiler, repair pass, and verification.
- `questgen/domain.py` - shared PDDL domain.
- `questgen/pddl.py` - small PDDL parser and STRIPS planner.
- `questgen/play.py` - text interface for playing generated quest series.
- `questgen/verify.py` - planner-based verification for generated quests.
- `quests/generated/ash_bell/` - generated quest series with `domain.pddl`, `quest_*.json`, `quest_*.pddl`, plans, prompt, and metadata.
- `raport.md` - project report.

## Generation

The default model is now `gemma3:4b`, which is much lighter than `qwen3.6:latest` and worked reliably on this machine.

```bash
python3 -B -m questgen.generator --mode compact --model gemma3:4b --out quests/generated/ash_bell --prompt "After years away, the hero returns to their childhood village and discovers that an ancient bell beneath the mine is waking ash-born shadows. The story should feel like a dark fairy tale, but end with hope for the village."
```

The generated metadata currently reports:

```json
{
  "model": "gemma3:4b",
  "used_fallback": false,
  "generation_strategy": "ollama_compact_draft_then_symbolic_pddl_compilation"
}
```

If the model is unavailable, the deterministic English fallback can still recreate a valid series:

```bash
python3 -B -m questgen.generator --mode fallback --out quests/generated/ash_bell --prompt "After years away, the hero returns to their childhood village and discovers that an ancient bell beneath the mine is waking ash-born shadows. The story should feel like a dark fairy tale, but end with hope for the village."
```

## Verification

```bash
python3 -B -m questgen.verify --series quests/generated/ash_bell
```

Expected result:

```text
OK   quest_01_quest-1.pddl: 5 actions
OK   quest_02_quest-2.pddl: 7 actions
OK   quest_03_quest-3.pddl: 6 actions
```

## Playing

Interactive text mode:

```bash
python3 -B -m questgen.play --series quests/generated/ash_bell
```

The text menu includes story-progressing actions, optional STRIPS-backed exploration actions, and side choices with consequences. Examples include revealing a hidden route with an item, provoking an NPC so a guard becomes hostile, getting wounded in a brawl, and using a healing tonic.

Automatic full playthrough:

```bash
python3 -B -m questgen.play --series quests/generated/ash_bell --auto
```
