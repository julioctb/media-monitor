# Political analysis with traceable evidence
Objective: implement the approved political-advisory plan with a configurable principal monitored person. Branch: `feat/digest-brief-v3`; baseline: `3905ceffa50e88963a1fe18bc4f891925642b166`.
Delivery: `auto-chain`, `feature-branch-chain` chosen by the user; local commits only, no publication/deployment. Runners: `.venv/bin/python -m pytest backend/tests -q`; frontend check, Vitest, build.

## Specs

- **S1 — Audit-derived scope.** User: «analiza el flujo de interpretacion de noticias de media monitor, identifica errores, inconsistencias, riesgos, no hagas cambios en el codigo, el objetivo es establecer un prompt que pueda generar un analisis de la informacion y se presenta a politicos, gobernantes, candidatos y / o rectores, esto ya se establece en el focus person». The original read-only restriction was superseded for local implementation by S4; historical-data repair and remote publication remain excluded.
- **S2 — Editorial voice.** User: «elabora un plan, y si quiero que el sistema tenga un tono se asesor politico, ademas de entregar el analisis trazable». Document facts / political interpretation / recommended attention distinctly; do not mistake schema tests for editorial validation.
- **S3 — Monitored subject, not necessarily reader.** User: «focus person es el nombre de una persona que esta en configuracion como palabra clave, es necesario tenerla? , la intencion es que esta persona es a la que se le da el segimiento de las noticias, quiero que el programa pueda usarse en un futuro a otras personalidades». Reuse tenant-scoped `digest_focus_person_id`; distinguish identity, keyword searches, additional watchlist subjects and readers. No hardcoded person or institution.
- **S4 — Execution authorization.** User: «ejecuta el plan». Canonical approved plan: `/Users/julioctb/Hermes/.hermes/plans/2026-10-25_164746-media-monitor-asesoria-politica-trazable.md`. Implement phase 1 as specified; technically decompose roadmap phases 2–5 before their source changes. No automatic production data writes, regeneration, deploy, push, or PR.
- **S5 — Delivery choice.** User: «1», selecting feature-branch chain. Keep tests/docs with behavior and separate verified work-unit commits. Current shared feature branch is preserved; do not switch it under the user.

### Phase 1 acceptance and boundaries

- T1: extend `docs/contrato-narrativa-del-digest.md` with the approved editorial contract and examples; mark future guarantees as future, update guided-schema status only.
- T2 backend: optional prompt-only `focus_person: {name, role, org}`, resolved with `queries.get_client_person` and effective client ID even when that person has no current mention. Unknown metadata stays null. Missing/deleted/foreign-client focus omits context without choosing a substitute. Existing no-focus prompt/projection remains unchanged.
- T2 configuration: one persisted selector `digest_focus_person_id`, replacing its hidden control and the keyword-only localStorage focus. Preserve a configured ID absent from a loaded catalogue, preserve independent watchlist and keyword CRUD; do not migrate local text to person identity. Remove dead handlers, badge and its unused CSS rule.
- No schema/migration, backend route, source-enrichment, summary-content, watchlist-policy, historical-data or general prompt rewrite in phase 1. Broader prompt, evidence and analytics changes belong to later tasks.
- Risk T2 backend: item 2, possible cross-client identity disclosure if tenant resolution is bypassed; independent verifier after self-checks. Configuration: medium, existing form contract reused.

## Tasks

- [x] **T1** → S2–S4 | inline | editorial contract + tracking | structural readback and diff checks passed | commit `9e1b9a6c`.
- [ ] **T2 backend** → S3–S4 | delegated direct | parallelism: backend prompt wiring + tests, disjoint from UI | self-checks passed: 103 focused, 596 full; parent 103 focused; independent tenant verifier pending | commit pending.
- [ ] **T2 configuration** → S3–S4 | delegated direct | parallelism: settings + keyword UI + tests, disjoint from backend | RED/GREEN + check/Vitest/build | commit pending.
- [ ] **T3** → S1,S4 | inline unless a named trigger fires | integrity of stories; technical decomposition pending | commit pending.
- [ ] **T4** → S1–S2,S4 | inline unless a named trigger fires | traceable evidence; technical decomposition pending | commit pending.
- [ ] **T5** → S1–S2,S4 | inline unless a named trigger fires | tone/risk/relevance/source semantics; technical decomposition pending | commit pending.
- [ ] **T6** → S1–S3,S4 | inline unless a named trigger fires | affected actors/dates/factual evolution; technical decomposition pending | commit pending.
- [ ] **T7** → S2–S4 | inline unless a named trigger fires | political advisory prompt; technical decomposition pending | commit pending.
- [ ] **T8** → S1–S4 | inline unless a named trigger fires | coherent postprocessing/fallback; technical decomposition pending | commit pending.
- [ ] **T9** → S1–S4 | inline unless a named trigger fires | traceable presentation; technical decomposition pending | commit pending.
- [ ] **T10** → S1–S4 | inline verification or fresh per-action worker | final deterministic/editorial evaluation | commit pending.

### Next-phase technical map (read-only, not implemented)

- T3.1: in `backend/app/summaries/builder.py`, eliminate the competing 0.2 cross-event single-linkage identity pass, preserving presentation cleanup and coverage. Pin recorded-distinct, unjudged gray, A–B–C bridge and loose-publication cases. Existing twin-merge tests need intentional replacement, not silent weakening.
- T3.2: in `backend/app/ingest/events.py`, reuse `is_aggregate_title` to exclude legacy aggregate titles/canonicals from future matching inputs; preserve client/time bounds, thresholds, media-first behavior and title-pool drift tests. Do not run healing/rebuild/deterministic historical merges. Negation is evidence-bearing; it does not by itself establish a distinct event or which report is true.
- T3.3: in `backend/app/summaries/digest.py`, compose cut material from eligible window publications rather than treating global event prose as current evidence; do not erase stored summaries. Inheritance must require compatible publication/material provenance, not event ID overlap alone. No wholesale historical reclustering.
- T4 proposal: frozen per-summary publication catalogue, optional versioned JSON metadata and field-level source-index references. Reuse `queries._outlet_of`, strict `digest_schema` entry validation, and stable publication IDs; preserve references during card reordering and compiled bullets. No relational migration or parallel parser. A reference proves provenance, not entailment, independence or factual truth.
- T4 product gate still to resolve before implementation: whether newly generated uncited prose must fall back or may publish clearly untraced; legacy payload compatibility must remain explicit. Full per-assertion verification cannot be claimed from field-level references.
- T4 revision boundary: parent spot-check confirmed `backend/app/api/summaries.py:77–95` restores only narrative/mode, not content. Do not attach current-cut evidence to restored old prose. Fully evidenced historical restoration would need separately designed snapshots; no historical migration is authorized.

## Log

- **L1 — Original request:** «analiza el flujo de interpretacion de noticias de media monitor, identifica errores, inconsistencias, riesgos, no hagas cambios en el codigo, el objetivo es establecer un prompt que pueda generar un analisis de la informacion y se presenta a politicos, gobernantes, candidatos y / o rectores, esto ya se establece en el focus person».
- **L2 — Editorial correction:** «elabora un plan, y si quiero que el sistema tenga un tono se asesor politico, ademas de entregar el analisis trazable».
- **L3 — Identity correction:** «focus person es el nombre de una persona que esta en configuracion como palabra clave, es necesario tenerla? , la intencion es que esta persona es a la que se le da el segimiento de las noticias, quiero que el programa pueda usarse en un futuro a otras personalidades».
- **L4 — Plan approved for execution:** «ejecuta el plan». Delivery follow-up: «1» = feature-branch chain. Date: 2026-10-25.
- **L5 — Baseline:** current branch `feat/digest-brief-v3`, HEAD `3905ceff`, no tracked diff. Ten pre-existing untracked backup/task files are unrelated and preserved. All-branch searches found no prior `_focus_person_context` or principal-selector implementation.
- **L6 — Forecast and route:** phase 1 approximately 550 authored added/deleted lines (backend/tests 190, configuration/tests 250, docs/tracking 110; forecast only). Work units: editorial contract, tenant-scoped prompt context, persisted configuration. Parallel backend/UI writers have disjoint edit surfaces; parent owns shared docs, tracking and git. No PR created.
- **L8 — T1 completed:** commit `9e1b9a6c7ca19625004348805cef2331c6e787db`; 139 additions / 6 deletions including tracking. Structural readback performed; trailing blank reported by diff check was removed and check rerun successfully. No functional RED applies to passive editorial documentation. Backend/UI writers launched once each with disjoint surfaces; next-phase read-only explorer launched for technical decomposition.
- **L7 — Environment:** scratch `/Users/julioctb/.hermes/cache/scratch/political-analysis.0Cmteh`; no dependency install, no deliberate LLM/network calls in tests. Engram unavailable: full-document mirror pending. The optional ephemeral-delegation skill file is absent; native `delegate_task` is available and used with explicit bounded missions.
- **L9 — T2 self-verification:** backend public-build test observed RED (1 failed) then GREEN; final 103 focused and 596 full tests passed under OS-level network denial. Parent reran 103 focused tests successfully. Fifteen new cases cover isolation/missing metadata/transport/gates; 12 baseline differential comparisons passed. Initial unsandboxed baseline run timed out at 420 s with no output; absence of outbound attempts cannot be certified. Corrected scratch baseline: 581 passed; an intermediate scratch module-alias harness failure was not a source defect. Final checks have no outstanding failure. Independent item-2 verifier remains pending.
- **L10 — Configuration self-verification:** behavioral RED/GREEN observed for selector, catalogue fallback and obsolete local focus removal. Final focused 33 passed, full Vitest 163 passed, svelte-check 0 errors/0 warnings, build exit 0. Parent focused rerun: 33 passed. Pre-existing CSRF-deprecation and unused Chart.js build warnings remain; server parser and tests unchanged. Isolated built-UI read-only probe pending.
