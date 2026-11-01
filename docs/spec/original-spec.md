# Original Spec: Automated Testing Agent Orchestrator

> **Provenance.** This is the seed document the project started from, preserved
> as written. It is **superseded where it conflicts** with
> [`../design/interview-decisions.md`](../design/interview-decisions.md) — most
> notably the project name (`val`, not `at-agent-orchestrator`) and the mutation
> strategy (mutations are applied by Rust-controlled tooling, not by an LLM
> editing source). The "SonarQube + AWS Bedrock addendum" referenced in the
> original request was **not included** with the paste; see open question Q-01
> in the decision record.

---

## 1. Purpose & Vision

`at-agent-orchestrator` (now **Val**): a high-performance, local/CI Rust CLI
tool. It acts as the state manager, syntax analyzer, and runtime execution
engine that orchestrates LLM agents to build rock-solid, production-grade test
suites across our codebases.

### The hard truth & core commandment

Standard AI agents optimize for speed, generate superficial tests (e.g.,
mocking everything out of existence), hallucinate interfaces, and take
shortcuts.

**The core design is resistance to shortcuts.** Every generated test must pass
real execution gates, possess mutation-tested assertion strength, and guarantee
that engineers can refactor underlying code with absolute confidence.

## 2. Target System Landscape

- Target codebases: Python (Pytest, Poetry) and TypeScript (Vitest/Jest, Playwright).
- Observability: SonarQube (Quality Gates, Branch Coverage, Mutation Report Ingestion).
- Automation CI: GitHub Actions.
- Infra platform: AWS (hosting runners, orchestrating isolated scratch containers, state backends).

## 3. Core Architecture of the Rust Tooling

The Rust binary is the deterministic platform that controls the probabilistic
nature of LLM agents. Four core modules:

### A. Codebase & Context Indexer (AST parser)
- Uses `tree-sitter` (`tree-sitter-python`, `tree-sitter-typescript`) to map exports, imports, functions, classes, and types.
- Generates a local JSON dependency graph identifying high-risk, low-coverage modules by parsing SonarQube API coverage data.

### B. Agent State Machine & Orchestrator
- Orchestrates a multi-agent loop using structured, typed JSON interfaces.
- Enforces a strict **"Test Execution & Validation Loop"**: Generate → Run locally → Parse errors → Mutate → Fix → Approve.

### C. Execution & Verification Sandbox
- Manages local or Docker-isolated sub-commands (`pytest`, `vitest`, `playwright test`).
- Parses raw terminal output and coverage XML (Cobertura, LCOV) to prove the agent *actually* improved structural coverage.

### D. CI & Infrastructure Synthesizer
- Scaffolds uniform GitHub Actions workflows and standard Docker test containers from local configuration schemas.

## 4. Multi-Agent Orchestration Architecture

```
[Rust Orchestrator]
 │
 ├──► 1. The Assessor   (Gap Finder)    ──► AST + SonarQube metrics
 ├──► 2. The Architect  (Test Specger)  ──► Scenarios (no code)
 ├──► 3. The Builder    (Code Generator)──► Strict code
 └──► 4. The Inquisitor (Verifier)      ──► Runs tests + injects mutations
```

**Agent 1 — The Assessor.** Find structural, semantic, and boundary holes.
*Anti-shortcut guard:* forbidden from looking only at line metrics; must
cross-reference SonarQube branch gaps and parse code paths for undocumented
edge cases, unhandled errors, and complex conditionals.

**Agent 2 — The Architect.** Design the testing strategy before writing code.
*Anti-shortcut guard:* cannot write implementation code. Outputs a strict
markdown file detailing test cases, concrete parameters, boundary values, mock
boundaries, and data states for unit & branch, integration (contract-based),
smoke & E2E (Playwright), and performance & stress.

**Agent 3 — The Builder.** Implement the Architect's spec in high-quality
TypeScript/Python. *Anti-shortcut guard:* strict types; no generic mocks that
bypass execution paths; mocks must conform to type declarations or interface
endpoints.

**Agent 4 — The Inquisitor.** Break the Builder's work. *Anti-shortcut guard:*
runs the code in the sandbox; if a test passes first try with zero
modifications, injects a minor semantic mutation (e.g. `x > 0` → `x >= 0`); if
the suite does not fail, reject and force the Builder to rewrite assertions.

## 5. Repo-Level Test Design Framework

```
┌────────────────────────────────────────────────────────┐
│ 1. SMOKE / HEALTH CHECKS (run in < 60s everywhere)     │
├────────────────────────────────────────────────────────┤
│ 2. UNIT & BRANCH TEST COVERAGE (strict isolation)      │
├────────────────────────────────────────────────────────┤
│ 3. INTEGRATION & CONTRACT (actual DB & API spies)      │
├────────────────────────────────────────────────────────┤
│ 4. PERFORMANCE / BURST (Locust / k6 benchmarks)        │
└────────────────────────────────────────────────────────┘
```

- **Smoke.** Python: entrypoint execution hooks, environment hydration, major AWS module imports. TypeScript: compilability and simple health-check endpoints.
- **Unit & branch.** Explicit assertions for every logical branch via parameter matrices. Property-based tests with Hypothesis (Python) and fast-check (TS) for core financial, analytical, or state-manipulation utilities.
- **Integration & contract.** Strict interface boundaries via contract verification schemas. Ephemeral test containers (PostgreSQL, Redis, LocalStack for DynamoDB/S3) rather than mock-everything structures.
- **Performance.** `locust` (Python) or `k6` (TS) scripts. Latency baseline assertions (e.g. p95 < 200 ms) on critical service functions.

## 6. Original Rust Initialization Tasks

1. Scaffold a Cargo workspace (`src/main.rs`, `src/ast/`, `src/agent/`, `src/sandbox/`, `src/sonar/`).
2. Define state models: Rust structs/enums for Agent State, Test Goals, File Diff Statuses, Verification Outcomes — `serde` boundaries.
3. Build the execution-loop sandbox: non-blocking `tokio::process::Command` wrapper — timeouts, stdout/stderr streaming, exit codes, artifact extraction.
4. Create prompt templates for Assessor, Architect, Builder, Inquisitor as embedded strings/template files with explicit Markdown-delimited boundaries.

Error handling via `thiserror`/`anyhow`. No placeholders.

## Appendix: Functional Testing Strategy Matrix

| Testing type | Python stack | TypeScript stack | Infra / observability |
|---|---|---|---|
| Smoke / health | `pytest -m smoke` | `vitest run --project smoke` | GitHub Actions step on push |
| Unit & branch | `pytest` + `pytest-cov` | `vitest` + `coverage-v8` | SonarQube Quality Gate ingestion |
| Mutation | `mutmut` or MutPy | `stryker-mutator` | Reports exported as mutation JUnit XML |
| Integration (AWS/DB) | `pytest` + LocalStack | `testcontainers-node` | Ephemeral Docker containers in runner |
| Performance | `locust` tasks | `k6` scripts | CloudWatch metrics / GitHub artifacts |
