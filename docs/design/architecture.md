# Architecture

Val is a Rust CLI (`val`) that **orchestrates LLM agents inside a deterministic
verification frame**. The frame is what you trust; the agents are what you
verify.

## 1. Principles

1. **Gates over prompts.** Anything that must be true is enforced by code that
   measures it, never by instructing a model.
2. **Agents propose, Rust disposes.** Agents emit schema-validated artifacts.
   Only Rust writes to the repo, runs tests, applies mutants, computes numbers,
   and opens PRs.
3. **Least authority per role.** Each role gets a tool policy, a path
   allowlist, and a budget; violations are rejected by the harness and
   recorded.
4. **Evidence or it didn't happen.** Every PR carries a machine-generated,
   signed evidence bundle recomputed from raw artifacts on a clean checkout.
5. **Value without the LLM.** Observing and gating are fully deterministic;
   the LLM is introduced only after those are trusted (see the
   [adoption ladder](../plan/rollout-plan.md)).
6. **Detect and adapt.** Val discovers each repo's conventions and respects
   them; standardization is opt-in per repo.
7. **Degrade gracefully.** No SonarQube capability, no Docker, no network: each
   absence reduces features but never correctness (nothing silently passes).

## 2. System context

```
                         ┌───────────────────────────┐
   Developer laptop ───► │            val CLI        │ ◄─── GitHub Actions
   (val assess/verify…)  │  (single static binary)   │      (reusable + fleet workflows)
                         └─────────────┬─────────────┘
        ┌───────────────┬──────────────┼──────────────┬────────────────┐
        ▼               ▼              ▼              ▼                ▼
  Repo(s) on disk   SonarQube     GitHub App     Agent runtime     State store
  (git worktrees)   (read/push)   (PRs, checks)  (trait)           (local → S3+DDB)
                                                    │
                                   ┌────────────────┴───────────────┐
                                   ▼                                ▼
                        Claude Code headless             Native Bedrock backend
                        (on Amazon Bedrock) — v1         (later, E38)
```

## 3. Crate layout (workspace of `val-*`)

| Crate | Responsibility | Roadmap |
|---|---|---|
| `val-cli` | clap commands, output modes, exit codes | E22 |
| `val-core` | domain types, JSON Schemas, run state machine, run store, errors | E01 |
| `val-config` | `val.toml`, fleet manifest, layering, `StateStore` trait | E02 |
| `val-index` | repo detection, tree-sitter symbols, branch obligations, git signals | E03 |
| `val-sandbox` | process runner, worktrees, container executor, egress policy | E04 |
| `val-report` | Cobertura / LCOV / JUnit / mutation parsers, diff coverage, integrity | E05 |
| `val-assess` | gap model, scoring, ranking, weak-test audit | E06 |
| `val-gates` | the verification gauntlet and verdict aggregator | E07 |
| `val-mutate` | mutation-engine trait + mutmut / Stryker adapters + targeted mutants | E08 |
| `val-runtime` | `AgentRuntime` trait, headless backend, fake/replay, conformance | E09 |
| `val-prompts` | role charters, templates, language packs, exemplar retrieval | E10 |
| `val-roles` | Architect / Builder / Reviewer drivers and the build–verify loop | E11–E13 |
| `val-policy` | autonomy levels, change classes, human gates, kill switch | E14 |
| `val-eval` | golden repos, seeded defects, scorecards | E15 |
| `val-sonar` | SonarQube client, ingestion, push, gate check | E17 |
| `val-github` | App auth, PR/check/comment lifecycle, CI state | E18 |
| `val-ci` | GitHub Actions workflow synthesis | E19 |
| `val-fleet` | workspaces, cross-repo graph, campaigns, scheduler | E33–E34 |

Crates depend downward only (`val-cli` → everything; `val-core` → nothing).
`val-gates` never depends on `val-runtime`: **the verifier cannot call an LLM.**
That boundary is enforced by a `cargo-deny` bans rule in CI (`E00-04`).

## 4. The run pipeline

```
 Observe ─► Assess ─► Specify ─► Build ◄──────────────┐
                                   │                   │ failures
                                   ▼                   │ (bounded)
                                 Verify ──(fail)───────┘
                                   │
                                 (pass)
                                   ▼
                              Adversarial review ─► Evidence bundle ─► Policy ─► PR
                                                                          │
                                                       report-only / draft / ready / auto-merge
```

| Stage | Actor | Output | Nature |
|---|---|---|---|
| Observe | Rust | `RepoProfile`, baseline coverage | deterministic |
| Assess | Rust (+ LLM semantic pass in S2) | ranked `Gap`s with evidence | deterministic core |
| Specify | **Architect** (LLM) | `TestSpec` (no code) validated by Rust | LLM, schema-checked |
| Build | **Builder** (LLM) | test files within a path allowlist | LLM, sandboxed |
| Verify | Rust gauntlet | `GateResult`s, `Verdict` | deterministic |
| Review | **Reviewer** (LLM, fresh context) | structured findings | LLM, isolated |
| Evidence | Rust | signed `EvidenceBundle` | deterministic |
| Policy | Rust | action per autonomy level | deterministic |

The run is an explicit **typed state machine** with a transition table, event
log, and checkpoints (`E01-03`..`E01-05`). Every state has a bounded retry
count and an *escalate-to-human* exit; nothing loops forever and nothing
"succeeds" by exhaustion.

## 5. Roles

| Role | Sees | May do | May never |
|---|---|---|---|
| **Assessor** | index, coverage, Sonar metrics, git signals | rank gaps, add semantic findings | write files |
| **Architect** | gap, symbols, conventions, existing tests | write the spec file | write code or tests |
| **Builder** | spec, source (read-only), conventions | write/edit files under test paths | edit source/config/CI; see mutants; mock the SUT |
| **Reviewer** | final diff, spec, rubric | emit findings | see Builder's reasoning; edit anything |
| *(Inquisitor)* | — | — | *Not an LLM role in Val; see `val-gates` + `val-mutate`.* |

The original spec's "Inquisitor" is split: deterministic verification and
mutation run in Rust; adversarial *judgment* is the independent Reviewer.

## 6. Agent runtime abstraction

```rust
// Illustrative contract (E09-01); not final API.
trait AgentRuntime {
    fn invoke(&self, req: RoleInvocation) -> Result<RoleResult, RuntimeError>;
}
struct RoleInvocation { role, prompt, workspace, tool_policy, output_schema, budget, timeout }
struct RoleResult     { output: Json /* schema-valid */, transcript, usage, stop_reason }
```

- **Headless backend (v1):** spawns `claude -p` per invocation with
  `stream-json`, Bedrock auth, generated allow/deny tool lists and
  `PreToolUse` hooks that enforce the role's path allowlist, inside the
  sandbox. Output is schema-validated; invalid output gets a bounded
  repair-reprompt, then fails.
- **FakeRuntime / ReplayRuntime:** deterministic tests of orchestration with
  recorded cassettes.
- **Conformance suite:** every backend must pass identical tests (schema
  adherence, tool-policy enforcement, timeout, budget stop) before it may be
  selected for a role.
- **Native Bedrock backend (later):** same trait, own tool-use loop, exact
  token accounting, deeper sandboxing.

## 7. Sandbox

- **Local worktree executor:** git worktree + scrubbed environment; for
  observe/gate on trusted code.
- **Container executor:** read-only source mount, writable overlay for tests,
  CPU/memory/pids limits, **no network by default**, egress via an allowlisting
  proxy (package mirrors, Bedrock endpoint, LocalStack), no ambient
  credentials. Required before any agent-written code runs.
- Declared artifact extraction only (`cobertura.xml`, `lcov.info`,
  `junit.xml`, mutation JSON), size-capped and integrity-checked.

## 8. Data model highlights

`RepoProfile`, `Gap` (stable id, evidence, risk score), `BranchObligation`,
`TestSpec` (scenarios, boundaries, mock boundaries with justification, layer),
`GateResult`, `Verdict` (`Pass | Fail | NeedsHuman`), `EvidenceBundle`,
`PolicyDecision`. All are `serde` types with generated JSON Schemas, versioned
with a compatibility policy (`E01-02`).

## 9. Config, state, and ratchets

- `val.toml` (per repo): conventions stance, commands, thresholds, risk tiers,
  sandbox, per-role models.
- Fleet manifest (central): repos, owners, tiers, adoption stage, Sonar keys.
- **Ratchets:** per-module floors for branch coverage and mutation score that
  can only rise; exemptions require a justification and an expiry
  (`E02-05`). This is the mechanism for incremental adoption on legacy code:
  *never worse, steadily better*.
- State behind a `StateStore` trait: local files (v1) → S3 + DynamoDB.

## 10. SonarQube

Treated as an **optional enrichment**, probed first (`E17-01`):

| Capability | If present | If absent (fallback) |
|---|---|---|
| Per-file branch coverage, complexity, hotspots | merged into gap ranking | local coverage run + local complexity (`E03-08`) |
| Quality-gate status for branch/PR | hard check on Val PRs | gate evaluated on main only; Val's own gates remain blocking |
| Coverage import | Val-verified reports pushed via scanner | none needed |
| Mutation / test-quality results | external issues or custom measures | evidence bundle + PR summary only |

## 11. Observability of Val itself

`tracing` spans per run/role/gate with correlation IDs; metrics catalog;
outcome KPIs (acceptance rate, revert rate, mutation uplift, escaped defects,
cost per merged PR); dashboards and alerts (E21). Cost is accounted per call
and enforced by budgets (E20).

## 12. Security posture (summary)

Threat model in `E16-01`. Key controls: repo content treated as untrusted data
(prompt-injection defenses), container sandbox with egress allowlist, no
secrets in model context or sandbox, least-privilege GitHub App, OIDC to a
scoped Bedrock role, Bedrock invocation logging, signed releases and pinned
Actions, append-only audit log of every policy decision.
