# Val

**AI test automation that can't take shortcuts.**

Val (short for *validate*) is a planned Rust CLI that orchestrates LLM agents
to build strong, trustworthy test suites across many Python and TypeScript
repos, so engineers can change code confidently and catch live issues early.

Its central idea: **agents propose, deterministic code disposes.** Every
generated test must pass real execution gates (branch coverage from raw
reports, mutation score, fail-before/pass-after, flake checks, anti-pattern
lint, independent review) before a human ever sees it. And because those
gates are useful on human-written tests too, Val is adopted **incrementally**:
observe first, then gate, then specify, then assist, with no LLM required for
the first two rungs.

> Status: planning. This repository currently holds the design, a
> dependency-graph roadmap (42 epics, 331 issues), and the tooling to explore
> it. The Rust workspace starts in milestone M0.

## See the plan

```sh
mise run roadmap:view        # builds and opens the visual roadmap + docs
# or, without mise (Python 3.11+, stdlib only):
python3 tools/roadmap/val_roadmap.py view
```

The viewer has an overview, a milestone board, an interactive dependency graph,
the per-repo **adoption ladder**, and all docs rendered with issue ids linked.

Other handy commands: `mise run roadmap:ready` (what to start now),
`mise run roadmap:path -- --stage S3` (critical chain to the first agent PRs),
`mise run roadmap:stage -- S1` (work required for the Gate stage),
`mise run roadmap:check` (validate the graph).

## Read the docs

| Start here | |
|---|---|
| [Implementation plan](docs/plan/implementation-plan.md) | What gets built, in what order, with hubs, risks, and parallel lanes |
| [Rollout plan](docs/plan/rollout-plan.md) | How repos adopt Val one reversible step at a time; pilots, ratchets, promotion rules, metrics |
| [Architecture](docs/design/architecture.md) | Crates, pipeline, roles, runtime abstraction, sandbox, SonarQube |
| [Anti-shortcut catalog](docs/design/anti-shortcut-gates.md) | 25 known shortcuts and the deterministic gate that defeats each |
| [Interview decisions](docs/design/interview-decisions.md) | Every design decision, assumption, and open question |
| [Roadmap format](docs/roadmap-format.md) | How the roadmap data and tooling work |
| [Original spec](docs/spec/original-spec.md) | The seed document (superseded where it conflicts) |

## Repository layout

```
docs/        design, plans, original spec
roadmap/     the roadmap as data (TOML): milestones, adoption stages, epics, issues
tools/       roadmap tooling (Python, stdlib only) and its tests
mise.toml    optional task shortcuts
```

## License

MIT. See the LICENSE file.
