# Interview Decisions & Assumptions

The outcome of the design interview that produced this roadmap. Every decision
here is referenced by roadmap issues; if a decision changes, change it here
first and then fix the affected issues.

## Decisions

| # | Area | Decision | Consequence |
|---|---|---|---|
| D-01 | Name | Binary `val`; Cargo workspace of `val-*` crates. Replaces `at-agent-orchestrator`. | Crate layout is fixed by ADR-002 (`E00-02`). |
| D-02 | Agent runtime | A Rust `AgentRuntime` **trait**. The **Claude Code headless** backend (on Bedrock) ships first; a **native Bedrock** backend is a later epic. | Gates, sandbox, and evidence are backend-independent. A conformance suite (`E09-08`) lets a second backend be proven equivalent. |
| D-03 | Run targets | Day one: developer-laptop CLI and GitHub Actions. AWS-hosted workers come later. | Container sandbox must work on laptops and GHA runners alike. |
| D-04 | Autonomy | **Tiered by risk.** Levels from report-only to auto-merge for narrow change classes, governed by a policy engine. | Policy engine is its own epic (`E14`); every write path consults it. |
| D-05 | Top pain | Low / shallow coverage on **existing** code. | Roadmap leads with assessment, characterization tests, and test-quality audit of *existing* tests. |
| D-06 | Acceptance bar | All of: mutation score, branch coverage from real reports, fail-before/pass-after proof, flake/determinism checks. Plus anti-pattern lint, diff policy, mock fidelity, independent review. "This is not exhaustive; agent-written tests and code get the most scrutiny; no shortcuts; reliability is the goal." | The gauntlet (`E07`) is the heart of the product. See [anti-shortcut gates](anti-shortcut-gates.md). |
| D-07 | Conventions | **Mixed per-repo policy.** Default detect-and-adapt; a repo may opt in to standardization. | `val.toml` carries a `conventions` stance (`E02-01`). |
| D-08 | Runtime dependencies | AWS services (S3/DynamoDB/SQS/Lambda), relational DB, queues/cache, third-party HTTP APIs. | Integration layer pack (`E26`). |
| D-09 | Tier-one data product concerns | First wave: data contracts & quality, delivery semantics, resilience & fault injection, security/privacy/IaC. | Layer packs `E29`–`E32`. Other concerns in backlog `E41`. |
| D-10 | Live issue signals | CloudWatch alarms/logs, bug tickets (GitHub Issues / Jira), otherwise ad hoc. | Feedback-loop epic (`E36`) includes defining a baseline signal set (`E36-07`). |
| D-11 | Scrutiny layers (v1) | Independent adversarial reviewer; seeded-defect eval corpus for Val itself; signed evidence bundle per PR; human review gates. | Epics `E13`, `E15`, `E14`. |
| D-12 | CI topology | **Both**: central fleet workflow *and* per-repo reusable workflow. | `E19` ships the reusable workflow first (incremental adoption); the central workflow arrives with the fleet milestone. |
| D-13 | Ownership | A central platform/quality team operates Val; owning teams review PRs via CODEOWNERS. | Review routing in `E14-03`; reviewer guide `E39-09`; operating runbook `E39-10`. |
| D-14 | Models & cost | Per-role model config with budget caps (per run / repo / day / fleet). | `E20`. |
| D-15 | Sandbox | Container per task with an egress allowlist; no ambient credentials. | `E04-03`, `E04-04`, `E04-06`. |
| D-16 | Stack | Python (Poetry **and** uv/pip), TypeScript (Vitest **and** Jest), pnpm workspaces and plain npm. | Language packs `E23`, `E24`. |
| D-17 | SonarQube depth | Read metrics to rank gaps; push results back; quality gate as a hard check. Provisioning via API is a later, optional step. | `E17`. Edition is unknown → capability probe first (`E17-01`). |
| D-18 | GitHub auth | GitHub App. | `E18-01`. |
| D-19 | Config & state | `val.toml` per repo + central fleet manifest + baselines/history in S3+DynamoDB (local files first). | `E02`. Storage behind a `StateStore` trait. |
| D-20 | Cross-repo | Dependency graph, downstream impact testing, consumer-driven contracts, shared test-utilities library. | `E33`. |
| D-21 | Scale | 10–50 repos at maturity. | Fleet design targets this range; sharding/tenant isolation is out of scope. |
| D-22 | Bedrock | Enabled in one AWS account. | Multi-account/central-gateway topology is deferred to an ADR (`E37-10`). |
| D-23 | SonarQube hosting | Company-managed; edition probably *Community/unknown*. | Assume **no** branch/PR analysis until the probe proves otherwise; every Sonar feature has a local fallback (`E17-11`). |
| D-24 | Project priority | **Incremental adoption.** Every milestone must deliver standalone value, and the earliest milestones must need no LLM at all. | Drives the adoption ladder in [rollout plan](../plan/rollout-plan.md). |
| D-25 | Roadmap form | The roadmap lives in this repo as a validated dependency graph (`roadmap/`), viewable via `mise run roadmap:view`. GitHub issues will be generated from it later (`E40-04`). | Single source of truth; no drift between plan and issues. |

## Design stances adopted during the interview

These were proposed by the facilitator and accepted implicitly. Challenge them
if they feel wrong.

1. **The gates are the product; the loop is a commodity.** Anti-shortcut
   guarantees live in deterministic Rust gates around the agents, never in a
   prompt.
2. **Mutations are applied by Rust, not by an LLM.** The spec's "Inquisitor
   manually injects mutations" lets a model grade its own homework. Real
   mutation tools plus Rust-applied targeted mutants replace it. An LLM may
   *propose* candidate mutants (`E08-07`); it never edits source.
3. **The Builder and the Reviewer never share context**, and the Builder is
   shown behavior-level feedback, not the specific mutant (avoids overfitting
   assertions to the mutant, `E08-08`, `E12-07`).
4. **Ship the verifier before the generator.** The gauntlet is valuable on
   human-written tests too, and must exist before any agent is allowed to
   write a line.
5. **Agents never fix source to make tests pass.** Suspected source bugs are
   reported as findings; characterization tests of questionable behavior are
   explicitly marked and flagged for human review (`E12-03`).
6. **Every claim is evidence.** Agents report; Rust measures. Numbers in a PR
   come from raw reports on a clean checkout (`E05-08`, `E07-05`).

## Open questions

| ID | Question | Needed by | Default if unanswered |
|---|---|---|---|
| Q-01 | The SonarQube + Bedrock addendum was not included in the original paste. Please provide it. | M1 | Assumptions in D-17, D-22, D-23 stand. |
| Q-02 | SonarQube edition and version; are branch/PR analysis and the `api/measures` and external-issue import endpoints available to a service token? | M1 (`E17-01`) | Assume Community Build, main-branch-only analysis. |
| Q-03 | Which 3–5 repos are pilot candidates (≥1 Python, ≥1 TypeScript)? Selection criteria in `E39-01`. | M1 | Platform team nominates. |
| Q-04 | IaC choice for Val's own AWS resources (CDK vs Terraform vs CloudFormation). | M4 (`E37-01`) | Match existing org practice. |
| Q-05 | Contract-testing approach (Pact broker vs schema-based). | L (`E26-06`) | Schema-based first. |
| Q-06 | Are any repos classified so that source may not be sent to an LLM, even via your Bedrock account? | M3 (`E16-06`) | Treat none as restricted. |
| Q-07 | Branch protection / required-check policy on target repos; can the GitHub App be installed org-wide? | M1 (`E18-08`) | Assume App install requires an org-owner approval. |
| Q-08 | Mutation-testing runtime budget acceptable in PR checks (minutes)? | M2 (`E07-07`) | Diff-scoped, ≤ 10 min, otherwise nightly. |
