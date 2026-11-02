# Implementation Plan

How Val gets built, in what order, and why. The plan is the *roadmap graph* in
`roadmap/` (42 epics, 331 issues, ~480 dependencies at time of writing) plus
this narrative. For *how repos adopt* what gets built, read the
[rollout plan](rollout-plan.md). Numbers below are a snapshot; the source of
truth is the data (`mise run roadmap:stats`).

## 1. Sequencing strategy

The single most important sequencing decision, recorded in
[the interview decisions](../design/interview-decisions.md) (D-24):

> **Every milestone ships something a team can use on its own, and the first
> two need no LLM at all.**

That produces five rules:

1. **Verifier before generator.** The gauntlet (`E07`) is useful on
   human-written tests, and must exist before any agent is allowed to write a
   line. It is built in M2, *before* the agent runtime (M3) and the Builder
   (M4).
2. **Observe before intervene.** M1 delivers a ranked, evidence-backed gap
   report with zero writes. It also produces the baseline every later claim is
   measured against.
3. **Gates first within every layer.** In each layer pack (smoke, integration,
   performance, data, ...) the deterministic gate lands before the generator,
   so even hand-written tests in that layer are verified.
4. **Thin slices, then breadth.** Each milestone first builds a walking
   skeleton through one Python repo, then widens to TypeScript and monorepos.
5. **Degrade, never fake.** Every optional dependency (SonarQube, Docker,
   network, LLM) has a defined fallback; absence reduces capability but never
   lets something pass silently.

## 2. Milestones at a glance

Effort points are relative (S=1, M=2, L=4), not calendar time. "Unlocks"
refers to the repo-level [adoption ladder](rollout-plan.md).

| Milestone | Unlocks | Issues | Points | What a team can do afterwards |
|---|---|---|---|---|
| **M0 Foundations** | - | 22 | 33 | Nothing yet; a governed workspace, ADRs, release pipeline, threat model |
| **M1 Observe** | S0 | 46 | 76 | `val assess` any repo: ranked gaps with evidence, baseline coverage, weak-test audit |
| **M2 Gate** | S1 | 48 | 89 | Advisory then blocking CI check for diff-coverage, mutation, flake, anti-patterns; ratchets |
| **M3 Specify** | S2 | 42 | 77 | Architect-written test specs for top gaps, reviewable by humans |
| **M4 Assist** | S3 | 46 | 79 | Val opens PRs with tests + signed evidence; humans review 100% |
| **L Layer packs** | optional | 56 | 102 | Per-layer gates/generators: smoke, integration, perf, E2E, data, delivery, resilience, security |
| **M5 Autonomy** | S4 | 14 | 27 | Auto-merge for narrow low-risk classes; kill switch; ratchet bumps |
| **M6 Fleet** | S5 | 27 | 48 | Campaigns across 10-50 repos; cross-repo impact testing; shared test utilities |
| **M7 Closed loop & scale** | S6 | 30 | 61 | Incidents become regression tests; AWS workers; native Bedrock backend |

Cumulative work to reach each rung (closure of dependencies):
S0 ≈ 68 issues / 109 pts · S1 ≈ 116 / 198 · S2 ≈ 158 / 275 · **S3 ≈ 204 / 354**
· S4 ≈ 218 / 381 · S5 ≈ 247 / 431 · S6 ≈ 280 / 496.
Reproduce with `mise run roadmap:stage -- S3`.

## 3. Milestone detail

### M0 - Foundations

**Goal:** a buildable, governed workspace that holds itself to the bar it will
enforce on others.

- Decisions first, in parallel: ADRs `E00-01` (runtime trait), `E00-02`
  (crates), `E00-08` (topology), `E00-09` (determinism), and the threat model
  `E16-01`.
- Then the workspace `E00-03`, CI `E00-04`, release `E00-06`, and the domain
  model `E01-01`..`E01-07`.
- **Dogfooding starts here:** `E00-05` puts branch coverage and
  `cargo-mutants` ratchets on Val's own core crates. If Val can't hold Val to
  its bar, it has no standing to hold others.
- Roadmap tooling (`E40-01`..`E40-03`) is already done in this repo.

**Hub risk:** `E00-02` -> `E00-03` -> `E01-01` sit upstream of ~250 issues.
Do these first, small, and fast.

### M1 - Observe (stage S0)

**Goal:** point Val at any repo and get a trustworthy ranking of where testing
is weak. No LLM, no writes.

Build order (walking skeleton → breadth):

1. Execution primitives: `E04-01` runner, `E04-02` worktree executor,
   `E04-07` artifact extraction.
2. Reports: `E05-01`/`E05-02` parsers → `E05-03` normalized model.
3. Python slice end to end: `E03-01` detector → `E03-02` command discovery →
   `E23-01`/`E23-02` Python pack → `E06-02` baseline run → `E03-03`/`E03-05`
   obligations → `E06-03` → `E06-04` **`val assess`**.
4. Breadth: TypeScript (`E03-04`, `E24-01`, `E24-02`), pnpm workspaces
   (`E03-10`), complexity fallback (`E03-08`), git signals (`E03-07`).
5. SonarQube as enrichment: probe `E17-01` first, then `E17-02`..`E17-04`,
   and the no-Sonar parity check `E17-11`.
6. Rollout work in parallel: pilot selection `E39-01`, org policy inventory
   `E18-08` (can block pilots), baselines `E39-02`, the S0 pilot `E39-03`.

**Exit:** gap report on 3-5 pilots (Python and TypeScript), owners agree the
top-10 is right, works with and without Sonar.

### M2 - Gate (stage S1)

**Goal:** deterministic verification of any test change, advisory then
blocking, with ratchets.

- Framework: `E07-01` → gates `E07-02`..`E07-10` → aggregator `E07-11` →
  **advisory mode `E07-12`**.
- Mutation: `E08-01`..`E08-06` (mutmut, Stryker, Rust-applied targeted
  mutants).
- Isolation: container executor `E04-03`, images `E04-05`, scheduler
  `E04-08`, secrets hygiene `E04-06`.
- Integrity: report integrity `E05-08`, diff coverage `E05-04`.
- Ratchets: `E02-05`.
- CI: reusable workflow `E19-01`, synthesizer `E19-03`, security lint
  `E19-07`.
- Trust: red-team corpus `E07-14` (each gate must reject its known-bad
  tests).
- Rollout: S1 pilot `E39-04`, playbook `E39-05`.

**Exit:** advisory gate running on pilot PRs; false-positive rate under
threshold; every catalog shortcut rejected by a red-team test.

**Why this is the pivotal milestone:** it is where Val starts paying for
itself *without any AI*, and where the trust model gets built before anything
needs trusting.

### M3 - Specify (stage S2)

**Goal:** introduce the LLM where it can do the least harm and the most
learning: read code, write a spec.

- Runtime: `E09-01` trait → `E09-02` headless backend → `E09-03`
  structured output → `E09-04` role tool policies; `E09-05` fake/replay for
  tests; `E09-07` Bedrock auth.
- Prompts: `E10-01`..`E10-06`.
- Roles: Assessor semantic pass `E06-07`, Architect `E11-01`..`E11-07`.
- Money: `E20-01`..`E20-03`, dry-run `E22-04`.
- Evaluation: golden repos `E15-02`/`E15-03`, defect seeding `E15-04`,
  honeypots `E15-06`.
- Security: injection defenses `E16-02`, data policy `E16-06`.

**Exit:** owners rate specs useful; eval baseline recorded; budget caps proven.

### M4 - Assist (stage S3)

**Goal:** Builder + independent Reviewer produce PRs that pass the full
gauntlet, with signed evidence, reviewed 100% by humans.

- Builder `E12-01`..`E12-08`, Reviewer `E13-01`..`E13-03`.
- Evidence: `E13-04` bundle → `E13-05` signing → `E13-06` PR body.
- PR lifecycle `E18-03`, CI reading `E18-05`, workflows `E19-04`, OIDC `E19-06`
  / `E37-02`.
- Eval as a release gate: `E15-05`, `E15-07`, prompt regression `E10-07`.
- Hardening: egress allowlist `E04-04`, hermetic installs `E04-09`, sandbox
  red team `E16-07`, mutation-in-Sonar `E17-08`.
- Pilots: Python `E39-07`, TypeScript `E39-08`, reviewer guide `E39-09`.

**Exit:** acceptance rate and mutation uplift meet targets; zero gate-bypass
incidents; eval scorecard gates every Val release.

### L - Layer packs (parallel track, after M4)

Each pack follows **charter → gate → generator → pilot** and is independently
adoptable. Suggested order for the stated estate (tier-one data products on
AWS):

1. **Smoke** `E25`: cheapest, universal; also feeds post-deploy checks.
2. **Integration & contract** `E26`: unlocks real dependencies for everything
   after it.
3. **Data contracts & quality** `E29`, **delivery semantics** `E30`,
   **resilience** `E31`, **security/privacy/IaC** `E32`: the first-wave
   tier-one concerns.
4. **Performance** `E27` and **E2E** `E28`: as repo need dictates.

### M5 - Autonomy (stage S4)

Policy model and engine `E14-01`/`E14-02`, human gates `E14-03`, auto-merge
`E14-04`, **kill switch `E14-05`**, promotion rules `E14-06`, audit log
`E14-07`, metrics `E21-02`/`E21-04`, ratchet bumps `E19-09`, runbook `E39-10`.
Exit includes a kill-switch game day.

### M6 - Fleet (stage S5)

Manifest `E02-03`/`E34-01`, campaigns `E34-02`, scheduler `E34-03`, workers
`E34-04`, cross-repo graph `E33-02`, blast radius `E33-03`, downstream impact
tests `E33-04`, consumer-driven contracts `E33-05`, shared test-utils
`E33-06`..`E33-08`, central workflow `E19-05`, quotas `E20-06`, dashboards
`E21-05`, wave plan `E39-12`.

### M7 - Closed loop & scale (stage S6)

Signals `E36-01` → incident-to-test `E36-02` → escaped-defect attribution
`E36-06`; canaries `E36-04`; AWS workers `E37-05`/`E37-06`; S3+DynamoDB state
`E02-06`/`E37-04`; native backend `E38-*` (only if the spike `E38-01` says the
headless backend is the constraint).

## 4. Dependency hubs and the critical chain

The issues whose delay blocks the most downstream work (transitive dependents):

| Issue | Blocks | Note |
|---|---|---|
| `E00-02`, `E00-03` | ~300 | Do first; keep tiny |
| `E01-01` core types | ~256 | Types churn is the biggest rework risk; review hard |
| `E04-01` process runner | ~187 | Everything executes through it |
| `E03-01` repo detector | ~135 | |
| `E04-02` worktree executor | ~121 | |
| `E01-06` error taxonomy | ~109 | |
| `E05-01`/`E05-02`/`E05-03` report parsers | ~108 | Coverage truth underpins every gate |
| `E07-01` gate framework | ~108 | |
| `E03-03`/`E03-04` tree-sitter | ~103 | Branch obligations depend on these |
| `E04-03` container executor | ~101 | |

The *sequential* critical chain to the first agent PRs (S3) is short in effort
terms (~25 points, mostly gates and pilots) because the graph is wide: from
the fourth dependency layer on, roughly 15-47 issues sit at each depth and
can run in parallel (the whole graph is 15 layers deep). **The
real constraint is not effort; it is review bandwidth and pilot soak time.**
Plan capacity around reviewers, not just builders.

## 5. Working in parallel

Five lanes map to the roadmap's themes. Each lane can be one or more Claude
Code sessions plus a named human reviewer.

| Lane | Epics | First deliverable |
|---|---|---|
| **Engine** | E00, E01, E02, E04, E05 | Workspace, types, runner, report parsers |
| **Intelligence** | E03, E06, E17, E23, E24 | `val assess` on a Python repo |
| **Verification** | E07, E08, E15, E16 | Gate framework and red-team corpus |
| **Agents** | E09, E10, E11, E12, E13, E20 | Runtime trait and replay |
| **Integration & rollout** | E18, E19, E21, E22, E39 | Reusable workflow and pilots |

Rules that keep parallel work safe:

- **Contracts first.** `E01-01`, `E01-02`, `E09-01`, and `E07-01` define the
  seams; changes to them go through review by the lane that consumes them.
- **One issue, one PR,** sized for a single session. `L` issues
  (`E07-03`, `E08-04`, `E09-02`, `E19-03`, `E36-02`, `E37-05`, `E38-02`) are
  split before starting.
- **Roadmap hygiene:** update `status` in the TOML in the same PR that
  completes an issue; `mise run roadmap:check` runs in CI (`E40-06`).
- **WIP limit:** no more open PRs than reviewers can clear in a day. Review
  capacity is the scarce resource.

## 6. Decisions to schedule early

| Decision | Issue | Needed by | Why |
|---|---|---|---|
| Runtime trait, crate layout, topology | `E00-01`, `E00-02`, `E00-08` | M0 | Everything depends on them |
| Threat model | `E16-01` | M0 | Shapes sandbox and policy |
| SonarQube capability probe | `E17-01` | start of M1 | Edition is unknown (Q-02) |
| Org policy inventory (branch protection, App approval) | `E18-08` | M1 | Can block pilots |
| Mutation-in-Sonar approach | `E17-07` | M3 | Edition-dependent |
| IaC tool | `E37-01` | before M4 | OIDC role is on the M4 path |
| Contract-testing approach | `E26-06` | before L:integration | Pact vs schema |
| Shared test-utils scope | `E33-06` | before M6 | Governance and ownership |
| Native backend go/no-go | `E38-01` | M7 | Evidence from the eval corpus |

## 7. Risks and mitigations

| Risk | Likelihood / impact | Mitigation | Issues |
|---|---|---|---|
| Mutation testing too slow for PR checks | High / High | Diff-scoped, budgeted and seeded sampling, nightly full runs, AWS workers later | `E08-06`, `E07-07`, `E37-05` |
| False positives erode trust in the gate | High / High | Advisory-first, would-have-failed telemetry, red-team corpus, waivers with expiry | `E07-12`, `E07-14` |
| Agents overfit to mutants or lint rules | Medium / High | Held-out mutants, behavior-level feedback, reviewer, honeypots | `E08-08`, `E12-07`, `E15-06` |
| SonarQube edition lacks branch/PR analysis | Medium / Medium | Probe early; local fallbacks; Val's own gates stay blocking | `E17-01`, `E17-11` |
| tree-sitter obligations diverge from coverage tools | Medium / Medium | Reconciliation property tests; unmappable obligations reported | `E03-05`, `E06-03` |
| Claude Code CLI behavior drifts | Medium / Medium | Version pin, canary, conformance suite, trait seam | `E09-09`, `E09-08` |
| Cost runaway | Medium / Medium | Per-role budgets, hard stops, dry-run estimates | `E20-03`, `E22-04` |
| Reviewer fatigue and rubber-stamping | High / High | Small PRs, evidence-first PR body, PR volume caps, calibration | `E13-06`, `E34-07`, `E39-09` |
| Prompt injection from repo content | Low / High | Data/instruction separation, tool policy, gates ignore claims | `E10-08`, `E16-02` |
| Goodhart: mutation score or coverage gamed | Medium / High | Multiple independent metrics; escaped-defect tracking | `E36-06`, `E21-04` |
| Scope creep from layer packs | High / Medium | Charter → gate → generator → pilot; each independently shippable | `L` epics |

## 8. How to work a roadmap issue with Claude Code

1. Pick from `mise run roadmap:ready` (all dependencies done).
2. Read the issue's acceptance criteria and every doc it links; check the ADR
   index for related decisions.
3. Write the tests that encode the acceptance criteria first.
4. Implement; keep the change inside the issue's scope.
5. Hold the work to the same bar Val will enforce: no skipped tests, no lint
   suppression without a reason, no coverage-config edits. (Dogfood ratchets
   `E00-05` will fail the build otherwise.)
6. Set `status = "done"` in the roadmap TOML and run
   `mise run roadmap:check`.
7. Open a PR that links the issue id; one issue per PR.

## 9. Keeping the plan alive

- The graph is validated on every PR: unique ids, known dependencies, no
  cycles, and no dependency on a later milestone.
- When scope changes, change the TOML, not just prose; the viewer, stage
  closures, and critical chains recompute automatically.
- `E40-04` will export the graph to GitHub issues (parents, sub-issues,
  labels, milestones) and `E40-05` will sync status back, so the board and
  the repo never drift.
