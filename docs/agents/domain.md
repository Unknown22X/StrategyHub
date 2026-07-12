# Domain docs

How engineering skills should consume this repository's domain documentation
when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repository root.
- **`CONTEXT-MAP.md`** at the repository root if it exists; it points to one
  `CONTEXT.md` per context. Read each one relevant to the topic.
- **`docs/adr/`**: read ADRs that touch the area being worked on. In
  multi-context repositories, also check `src/<context>/docs/adr/` for
  context-scoped decisions.

If any of these files do not exist, proceed silently. Do not flag their
absence or suggest creating them upfront. The `/domain-modeling` skill creates
them lazily when terms or decisions are resolved.

## File structure

This is a single-context repository:

```text
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-example-decision.md
│   └── 0002-example-decision.md
└── src/
```

## Use the glossary's vocabulary

When naming a domain concept in an issue title, refactor proposal, hypothesis,
or test name, use the term defined in `CONTEXT.md`. Do not drift to synonyms
the glossary explicitly avoids.

If a needed concept is absent from the glossary, either reconsider whether the
project already has a better term or note the genuine gap for
`/domain-modeling`.

## Flag ADR conflicts

If an output contradicts an existing ADR, surface it explicitly rather than
silently overriding it:

> _Contradicts ADR-0007 — worth reopening because…_
