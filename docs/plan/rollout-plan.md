# Rollout Plan: Incremental Adoption

How teams and repos adopt Val without a big-bang commitment. This is the
companion to the [implementation plan](implementation-plan.md): that document
says what gets *built* and when; this one says how a repo *uses* it, one
reversible step at a time.

## 1. Principles

1. **Every rung is independently valuable.** A repo can stop at any stage and
   keep the value it has.
2. **Every rung is reversible,** with a documented rollback that costs minutes.
3. **No LLM until trust exists.** Rungs S0 and S1 use no model at all.
4. **Advisory before blocking,** blocking before autonomous.
5. **Evidence promotes; opinion does not.** A repo moves up only when
   measured exit criteria are met, with a recorded approver.
6. **Never worse, steadily better.** Ratchets protect legacy code: overall
   floors can only rise; new and changed code is held to the strict bar.
7. **Humans stay in control of volume.** PR caps, batching, and quiet hours
   keep Val from becoming noise.

## 2. Three independent axes of adoption

| Axis | Unit | Mechanism | Why separate |
|---|---|---|---|
| **Depth** | Repo | The stage ladder S0-S6 | How much of Val a repo trusts |
| **Breadth** | Test layer | Layer packs (smoke, integration, performance, E2E, data, delivery, resilience, security) | Repos need different layers at different times |
| **Strictness** | Module | Ratchets and thresholds per risk tier | Legacy modules start lenient and tighten |

A repo is described by a tuple: *stage* × *enabled layer packs* × *ratchet
floors*. All three live in `val.toml` and the fleet manifest.

## 3. The adoption ladder

Details, entry and exit criteria, and rollback for each rung are in the
viewer's *Adoption ladder* tab (`mise run roadmap:view`; data in
`roadmap/meta.toml`). Summary:

| Stage | Repo experience | LLM? | Writes to repo? | Human burden | Rollback |
|---|---|---|---|---|---|
| **S0 Observe** | Ranked gap report, baseline, weak-test audit | No | No | Read a report | Delete run dir |
| **S1 Gate** | CI check on PRs: diff coverage, mutation on changed code, flake, anti-patterns; ratchets | No | No (CI check only) | Fix or waive findings | Remove workflow / go advisory |
| **S2 Specify** | Architect-written test specs for top gaps | Yes (reads code) | Comments/files only | Review specs | Disable spec job |
| **S3 Assist** | Val opens PRs with tests + evidence | Yes | PRs only | Review 100% of PRs | Kill switch; close PRs |
| **S4 Autonomy** | Eligible test-only PRs auto-merge | Yes | Merges within policy | Spot-check; handle escalations | Demote in policy |
| **S5 Fleet** | Campaigns, cross-repo impact tests, shared utils | Yes | Many repos | Triage digests | Pause campaigns |
| **S6 Closed loop** | Incidents become regression tests | Yes | Via normal gated path | Review incident tests | Disable ingestion |

What each stage costs to *build*: S0 ≈ 68 issues / 109 points; S1 ≈ 116 / 198;
S2 ≈ 158 / 275; **S3 ≈ 204 / 354**; S4 ≈ 218 / 381; S5 ≈ 247 / 431;
S6 ≈ 280 / 496 (cumulative; see `mise run roadmap:stage -- S3`).

### Where the value shows up first

- **S0** answers "where are we weak?" with evidence - the conversation starter
  for every team.
- **S1** is where most of the durable value lies for the stated pain
  (*shallow coverage on existing code*): even before any agent writes tests,
  it stops new shallow tests from landing and lifts the floor as humans write
  better ones.
- **S3** is where the backfill of legacy coverage actually happens.

Teams that never want agents can stop at S1 and still get measurable benefit.

## 4. Pilot design

Pilots are how Val earns trust. They are timeboxed, instrumented, and each has
an explicit go/no-go.

### 4.1 Selecting pilots (`E39-01`)

Choose 3-5 repos with this mix:

| Criterion | Why |
|---|---|
| At least one **Python** and one **TypeScript** repo | Prove both stacks early |
| At least one **library** and one **service** | Different gap shapes |
| **Shallow existing coverage** (the stated pain) | Maximum visible lift |
| **Moderate criticality** | Real stakes, bounded blast radius |
| **Healthy CI** and low baseline flake | Val's signal isn't drowned in noise |
| **A supportive owner** who will give feedback | Fast calibration |
| Org policy not blocking (App install, branch protection) | See `E18-08` |

Avoid for pilots: the most critical service, repos in the middle of a
migration, and repos with chronically red CI.

### 4.2 Baseline (`E39-02`)

Before touching anything, record for each pilot: line and branch coverage, a
mutation-score sample on a few key modules, escaped bugs over the last
quarter, CI duration, and change-failure rate. Every later claim ("Val raised
coverage by X") is measured against this.

### 4.3 Pilot sequence

| Pilot | Stage | Timebox | Success criteria | Go/no-go |
|---|---|---|---|---|
| `E39-03` | S0 | until owners validate | Owners agree top-10 gaps are the riskiest; weights calibrated | Proceed to S1 |
| `E39-04` | S1 advisory → blocking | until false-positive rate is under target | Findings judged actionable; thresholds agreed; ratchet in place | Flip advisory to blocking |
| `E39-06` | S2 | N specs per pilot | Usefulness rating above the agreed bar | Proceed to S3 |
| `E39-07` | S3, Python | N PRs | Acceptance rate, mutation uplift, and review time within targets; zero gate bypass | Proceed to TypeScript |
| `E39-08` | S3, TypeScript (incl. pnpm package) | N PRs | Same targets | Proceed to S4 evaluation |

"N" and the targets are calibrated at the previous pilot, not guessed now.
Calendar dates are deliberately absent until team capacity is known; durations
are dominated by **pilot soak time and review capacity**, not build effort.

## 5. Per-repo onboarding playbook

Use `val onboard` (`E22-08`) to walk it; the playbook itself is `E39-05`.

**Before S0:** repo owner agrees to a read-only run → `val doctor` passes →
nominate a reviewer.

**S0 → S1 (Gate)**
1. Review the gap report with the owner; agree risk tiers for key modules.
2. Record baseline (`E39-02`).
3. Install the reusable workflow (`E19-01`), **advisory**.
4. Tune: review "would-have-failed" telemetry weekly; adjust rules (with
   reasons), add waivers (with expiry).
5. Agree thresholds per risk tier; set initial ratchet floors **at current
   values** (no immediate failures).
6. Flip to blocking for *new and changed code* first; legacy modules stay on
   the ratchet only.

**S1 → S2 (Specify)**
1. Confirm the data-handling policy for the repo (`E16-06`); set the budget.
2. Run the Assessor semantic pass + Architect on the top-N gaps.
3. Owner reviews specs; rejected specs are categorized and feed prompts.

**S2 → S3 (Assist)**
1. Enable `val-assist` for a small gap set; 100% human review.
2. Reviewers use the guide (`E39-09`): read the evidence bundle first, check
   the Reviewer's findings, spot-check behavior, and never merge on the
   evidence alone.
3. Track acceptance, review time, defects found by humans that gates missed
   (each is a bug in Val's roadmap).

**S3 → S4 (Autonomy)** only after promotion rules (`E14-06`) are met and the
kill switch has been exercised (`E14-05`, `E39-10`).

## 6. Ratchets: adopting on legacy code

The ratchet (`E02-05`, `E19-09`) is the mechanism that makes incremental
adoption safe for existing, shallow suites:

```
 baseline ─► floors = current values ─► every PR: no module may drop below its floor
                                          │
                       floors rise when main is green and a module improves
                                          │
          new/changed code is held to the strict tier threshold (diff-scoped)
```

- **Overall** coverage and mutation floors only rise.
- **Diff-scoped** thresholds apply the full bar to touched code, so legacy
  debt is paid down as the code is changed.
- **Waivers** need a reason and an expiry; expired waivers fail the check.
- **Weak tests count as weak:** coverage achieved by assertion-free tests is
  discounted in ranking (`E06-06`), so "80% coverage" can't hide shallow
  suites.

## 7. Autonomy promotion (proposed starting rules)

Thresholds below are **proposals to calibrate at the S3 pilot**, not commitments.

| Move | Evidence required | Approver |
|---|---|---|
| S3 → S4 for a repo | ≥ 30 merged PRs, acceptance rate ≥ 80%, zero escaped defects attributed to Val tests, zero gate-bypass incidents, kill switch drill done | Platform lead + repo owner |
| Auto-merge for *test-only* class | All gates + Sonar + CI green, evidence signed, cool-off window elapsed | Policy (automatic) |
| Source-touching changes | Never auto-merge; separate human-review PR (`E14-08`) | Human |
| Demotion | Any revert of a Val PR, a post-merge CI failure, a flake spike, or an escape attributed to a Val test | Automatic; resume needs a human |

## 8. Fleet expansion (stage S5)

Wave plan `E39-12`. Expand only when the previous wave is healthy.

| Wave | Repos | Entry criteria | Capacity check |
|---|---|---|---|
| 0 | 3-5 pilots | M1-M4 complete | Platform team + pilot owners |
| 1 | ~10 | Pilot go/no-go passed; playbook proven; dashboards live | Review load per team measured |
| 2 | ~25 | Wave 1 acceptance and revert rates within bounds; PR volume caps tuned | Bedrock quotas, budget approved |
| 3 | 25 → 50 | Wave 2 stable; cross-repo impact testing running | Fleet scheduler and AWS workers in place |

Within each wave, repos adopt per the ladder: most will sit at S1-S3; only
repos with a track record reach S4.

## 9. Metrics

Lead with *outcomes* the team actually cares about ("can we change code
confidently?"), and pair every efficiency metric with a quality counter-metric
to resist Goodhart's law (`E39-11`).

| Question | Primary metric | Paired guard-rail |
|---|---|---|
| Are tests stronger? | Mutation score on touched code (held-out set) | Escaped-defect rate |
| Is coverage real? | Branch coverage from raw reports | Weak-test ratio (assertion-free, over-mocked) |
| Can we change code safely? | Change-failure rate; time to merge | Revert rate |
| Is Val useful? | PR acceptance rate; spec usefulness rating | Reviewer time per PR |
| Is Val honest? | Honest-behavior rate on honeypots; gate-bypass incidents (target 0) | Escalation rate (is "needs human" being abused?) |
| Is it affordable? | Cost per merged PR; cost per killed mutant | Budget breach events |
| Is the suite healthy? | Flake rate; suite runtime | Quarantine age |

Review cadence: weekly during pilots (owners + platform), monthly per wave,
quarterly org-wide (`E39-11`).

## 10. Enablement and communication

- **Reviewer guide** (`E39-09`): under two pages; what the evidence means,
  what to distrust, how to escalate.
- **Opt-out and snooze:** owners can pause Val for their repo at any time
  (`E34-07`); this is a feature, not a failure.
- **Noise control:** per-repo and per-team PR caps, digest mode, quiet hours.
- **Transparency:** every Val PR links its evidence bundle, the spec, and the
  run report; every policy decision is in the audit log (`E14-07`).
- **Feedback loop:** recurring reviewer comments become rubric rules after
  validation on the eval corpus (backlog `E41-05`).

## 11. Stop-the-line conditions

Pause the relevant scope (kill switch `E14-05`) when any of these occur:

- A gate-bypass incident (a bad test merged that the gauntlet should have
  rejected).
- A secret or credential appears in any artifact, transcript, or PR.
- A Val PR causes a production incident or a post-merge CI break.
- Cost exceeds the hard budget cap unexpectedly.
- Reviewers report rubber-stamping (acceptance without comments for N PRs
  while the Reviewer flagged findings).

Each pause triggers a short retrospective; the fix is added to the roadmap
(usually as a new gate or red-team case) before resuming.

## 12. What we need from you

| Need | Used by | Open question |
|---|---|---|
| Pilot repo nominations (≥1 Python, ≥1 TypeScript) | `E39-01` | Q-03 |
| SonarQube edition/version and token scope | `E17-01` | Q-02 |
| The missing SonarQube + Bedrock addendum | M1 | Q-01 |
| Branch-protection and GitHub App install policy | `E18-08` | Q-07 |
| Acceptable mutation-run time in PR checks | `E07-07` | Q-08 |
| Any repos that may not send source to an LLM | `E16-06` | Q-06 |
| Team capacity (builders and reviewers) to turn effort points into dates | planning | - |
