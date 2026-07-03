# Implementation Checklist — Argus Analyst Workbench

A phased build order for recreating the design (see `README.md`) in a real codebase and
wiring it to the Argus backend (`argus_backend_spec.md`). Recommended stack if none exists:
**React + TypeScript**. Check items off as you go; each phase should be demoable.

> The bundled `Argus Workbench.dc.html` is a **design reference**, not code to ship. Match
> its look/behavior; use your own framework, components, and data layer.

---

## Phase 0 — Foundations
- [ ] Set up the frontend app (or a route/module in the existing app).
- [ ] Add fonts: **IBM Plex Sans** + **IBM Plex Mono** (weights 400/500/600/700).
- [ ] Encode **design tokens** from README (colors, type scale, radius, spacing, shadows)
      as theme variables / Tailwind config / CSS custom properties.
- [ ] Add helpers: `money(n)` (USD, 2 decimals), `riskColor(r)` / `riskBand(r)`
      (`≥0.7 HIGH red`, `0.4–0.7 ELEVATED amber`, `<0.4 LOW green`).
- [ ] Establish base primitives: `Card`, `Chip`/`Badge`, `Button` (primary red / green
      outline / ghost), `KeyValueRow`, `SectionHeader` (number badge + title + sub).

## Phase 1 — App shell & navigation
- [ ] Build the **nav rail** (brand, 4 nav items w/ icons + active state, SYSTEM panel,
      benchmark bar, user chip). Sticky, full height, 230px.
- [ ] Wire view routing/state: `overview | cases | live | ask`.
- [ ] Two-pane layout scaffold for Case files & Live triage (340px queue + fluid pane,
      independent scroll). Single-column scaffold for Overview & Ask.
- [ ] Toast system (bottom-right, action-colored left border, ~4.2s auto-dismiss).

## Phase 2 — Data layer
- [ ] Define the **Case** type: `{ id, truth, rec, risk, conf, alert{…}, sender[], counter[],
      velocity[], signals[], policy[], policyVerdict, criticPasses[], reasoning[],
      typical, flow{destKind,fanIn,zeroBal,isCashOut}, history[] }`.
- [ ] Load investigated cases from the backend (`argus_backend_spec §6/§11`). Keep the
      prototype's 6 mock cases as fixtures for Storybook/tests.
- [ ] Client state: `decisions`, `audit`, `pendingAction`, `rationaleText`, `threads`,
      `live` (pipeline), selections, `caseFilter`.

## Phase 3 — Overview
- [ ] Metric strip (4 cards), "What Argus does" + pipeline breadcrumb, benchmark table,
      agent roster grid. Mostly static; pull benchmark numbers from `results/metrics.csv`.

## Phase 4 — Case files (primary view)
- [ ] Queue column: filter chips (All/Escalated/Cleared) + selectable case rows
      (REC badge, risk %, risk meter, truth, status pill).
- [ ] Detail header: title + REC badge + ground-truth line + **risk gauge card**.
- [ ] **Agent trace strip** (6 done nodes + captions, horizontal scroll).
- [ ] Section 01 alert (sentence + 4 metric cards).
- [ ] Section 02 evidence: **baseline chart** (Signature A) + 3 key/value cards.
- [ ] Section 03 **money-flow diagram** (Signature B).
- [ ] Section 04 signal chips (severity colors).
- [ ] Section 05 policy table (fired/clear, verdict footer).
- [ ] Section 06 **critic revision loop** (Signature C).
- [ ] Section 07 decision fusion: **Analyzer-vs-Policy agreement** (Signature D) + reasoning.

## Phase 5 — Signature components (do these with care)
- [ ] **A. Baseline chart** — 15 history bars + glowing alert bar + dashed "typical" line +
      dynamic multiplier note.
- [ ] **B. Money-flow** — Sender → amount → Destination(mule/merchant/internal, colored,
      fan-in dots + note) → optional Cash-out; horizontal scroll.
- [ ] **C. Critic loop** — 1–2 passes; flagged (amber ⚠) → approved (green ✓); show the
      specific rejected claim.
- [ ] **D. Agreement** — Analyzer chip + Policy chip + agree/disagree pill (the CLEAR/0.55
      case must read as a *disagreement* resolved by fusion).

## Phase 6 — Human approval gate + audit (core guardrail)
- [ ] Gate state machine: **buttons → rationale composer (required, min 8 chars, live
      counter, Confirm disabled until valid) → decided (logged, with Undo)**.
- [ ] On confirm: write decision + **audit entry** (ts, actor, action, rationale), toast,
      flip queue status pill.
- [ ] Section 09 **audit trail** = seeded system events + appended human decision row.
- [ ] Persist decisions/audit to the backend audit object (`§9`); enforce "no action
      without explicit confirm + rationale" (`§8`).

## Phase 7 — Live triage
- [ ] Queue + Investigate button (states: idle → running/"Investigating…" → "Re-run").
- [ ] Idle empty-state.
- [ ] **Vertical agent timeline** driven by real streamed pipeline events (nodes
      pending→active(pulse)→done, log lines fill in); mirror status in nav-rail SYSTEM panel.
- [ ] On completion: reveal report (banner, alert cards, signals, critic passes) + reuse
      the Phase 6 gate.

## Phase 8 — Ask Argus
- [ ] Case chips + 3 suggested questions + composer (Enter submits).
- [ ] Chat thread (user + assistant bubbles).
- [ ] Answers **grounded only in the selected case's evidence/audit**; if unanswerable from
      the record, say so (route to the backend's grounded-QA over that case, per `§7/§9`).

## Phase 9 — Polish & QA
- [ ] Animations: `fadeUp` reveals, node pulse ~1.1s, subtle easing.
- [ ] Hover/focus states on all interactive elements; visible keyboard focus.
- [ ] Responsive rules (README): ≥1280px ideal; below ~1000px collapse queue into a
      list/dropdown and stack panes; keep money-flow/trace horizontally scrollable.
- [ ] Accessibility: semantic roles, `aria` on status pills/toasts, textarea label,
      color-contrast check on muted text, don't rely on color alone for fired/agree state.
- [ ] Replace inline SVG icons + CSS shield with the codebase's icon/brand system.
- [ ] Storybook stories for the 4 signature components across case variants (fraud vs
      legit, 1-pass vs 2-pass critic, agree vs disagree, cash-out vs merchant).

## Definition of done (frontend)
- [ ] All 4 views implemented and navigable; two-pane views scroll independently.
- [ ] All 4 signature components render correctly across every case in the fixture set.
- [ ] Approval gate enforces rationale + writes an audit entry; Undo reverts both.
- [ ] Live pipeline animates from real backend progress events; report + gate follow.
- [ ] Tokens/typography match the README; desktop responsive rules applied.
