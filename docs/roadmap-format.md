# Roadmap Format and Tooling

The roadmap is **data**, not prose: a dependency graph of epics and issues in
TOML, validated on every change and rendered by a stdlib-only Python tool.
Nothing to install beyond Python 3.11+.

## Commands

Run with `mise run <task>`, or directly with
`python3 tools/roadmap/val_roadmap.py <command>`.

| mise task | Command | What it does |
|---|---|---|
| `roadmap:view` | `view [--port N] [--no-open]` | Build the viewer, serve it at `http://127.0.0.1:8765`, open the browser |
| `roadmap:build` | `build` | Write `.roadmap-site/index.html` (self-contained, works offline) and `.roadmap-site/artifact.html` (bare fragment for publishing as a Claude artifact) |
| `roadmap:check` | `check` | Validate the graph; exit 1 with every problem listed |
| `roadmap:ready` | `ready [--milestone M] [--limit N]` | Issues whose dependencies are all done: where to start |
| `roadmap:path` | `path [--stage S \| --to ID]` | Longest remaining dependency chain |
| `roadmap:stage` | `stage S` | Everything required to reach adoption stage `S` |
| `roadmap:stats` | `stats` | Issues and effort points per milestone |
| `roadmap:test` | - | Unit tests for the tool |

Pass extra arguments after `--`, for example `mise run roadmap:path -- --stage S3`.

## The viewer

- **Overview:** totals, what is ready to start, the critical chain to the first
  agent-written PRs.
- **Roadmap:** a board of milestones, with each epic as a card.
- **Dependency graph:** epics overview (columns by first milestone; hover to
  trace dependencies), all issues, a single epic with its neighbors, or the
  minimal path to an adoption stage. Filter by milestone, search, highlight the
  critical chain, hide done work. Click anything for details; drag to pan,
  scroll to zoom.
- **Adoption ladder:** the per-repo stages with entry/exit criteria, rollback,
  and the exact amount of work each requires.
- **Docs:** every Markdown file under `docs/` (and the README), with roadmap
  ids like `E07-03` auto-linked to the issue.

## Files

```
roadmap/
  meta.toml              milestones (build order) and adoption stages (per-repo ladder)
  epics/NN-*.toml        epics and their issues (several epics per file is fine)
docs/                    narrative documentation, rendered by the viewer
tools/roadmap/           the tool (val_roadmap.py), viewer assets, tests
```

### Milestones vs stages

| | Milestone (`M0`..`M7`, `L`) | Stage (`S0`..`S6`) |
|---|---|---|
| Answers | What do we build next? | How much of Val may a repo use? |
| Defined in | `[[milestone]]` in `meta.toml` | `[[stage]]` in `meta.toml` |
| Linked by | an issue's `milestone` | a stage's `requires = [milestones]` |

A stage's required work is every issue in its `requires` milestones **plus
their transitive dependencies**. `L` (layer packs) is an optional parallel
track and is required by no stage.

Build order of milestones: `M0, M1, M2, M3, M4, L, M5, M6, M7`. An issue may
depend only on issues in the same or an earlier milestone in that order; the
validator rejects anything else, which keeps the plan honest.

### Epic

```toml
[[epic]]
id = "E07"                  # E + two digits
title = "Verification Gauntlet"
theme = "verify"            # colour family in the viewer
goal = "One sentence."
milestone = "M2"            # default for its issues
lang = ["rust"]             # default; also: python, typescript, gha, aws, any
size = "M"                  # optional default
type = "feature"            # optional default
```

### Issue

```toml
[[issue]]
id = "E07-03"               # epic id + two digits; the epic is derived from the prefix
title = "Gate: test anti-pattern linter"
type = "feature"            # feature | adr | spike | docs | chore | infra | test
size = "L"                  # S=1, M=2, L=4 effort points (L warns: split before starting)
milestone = "M2"            # override of the epic default
deps = ["E07-01", "E03-03"] # must exist, no cycles, not in a later milestone
status = "todo"             # todo | doing | done (done work costs 0 in critical chains)
summary = "What and why, in a sentence or two."
acceptance = ["Observable, testable criteria", "At least one is required"]
```

Write acceptance criteria so an agent (or a person) can tell when the issue is
done *and* so a test can be written for each.

## Validation rules

`check` fails on: malformed or duplicate ids; unknown epic, milestone, size,
type, or status; missing title, summary, or acceptance criteria; unknown or
self dependencies; dependency cycles; a dependency on a later milestone;
epics with no issues; stages naming unknown milestones.

## Effort points

Relative weights (S=1, M=2, L=4), **not calendar time**. They exist to compare
work, find the critical chain, and size stages. Convert to dates only once team
capacity (builders *and* reviewers) is known.

## Editing workflow

1. Change the TOML (and docs if the narrative changes).
2. `mise run roadmap:check` and `mise run roadmap:test`.
3. `mise run roadmap:view` to look at the result.
4. When completing work, set `status = "done"` in the same PR.

Planned: export to GitHub issues with sub-issues, labels, and milestones
(`E40-04`) and sync status back (`E40-05`).
