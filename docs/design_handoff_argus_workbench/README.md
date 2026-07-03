# Handoff: Argus — Fraud-Triage Analyst Workbench (Frontend)

## Overview
Argus is a multi-agent system that triages fraud alerts and produces analyst-ready
case files, with a **human approval gate** before any action. This handoff covers the
**analyst-facing frontend**: a dark "security-console" workbench where an analyst
reviews investigated cases, watches the agent pipeline run live on a queued alert,
approves/dismisses with a logged rationale, and asks grounded questions about a case.

The backend architecture, agents, tools, data, and evaluation harness are specified
separately in **`argus_backend_spec.md`** (included in this folder). This README is
about the **UI**; where the two overlap (case-file shape, agent names, statuses) they
are consistent.

## About the Design Files
The file **`Argus Workbench.dc.html`** in this bundle is a **design reference created
in HTML** — an interactive prototype that shows the intended look, layout, and behavior.
It is **not production code to copy directly**. It is authored as a single streaming
"Design Component" with inline styles and a small logic class; treat it as a visual +
behavioral spec.

Your task is to **recreate this design in the target codebase's environment** using its
established patterns and libraries. If no frontend exists yet, the recommended stack is
**React + TypeScript** (the prototype's state model maps cleanly to React
`useState`/`useReducer`), styled with whatever the team standardizes on (CSS Modules,
Tailwind, or styled-components). Wire the screens to the real Argus backend (the
`/agents` pipeline and per-case audit trail from `argus_backend_spec.md`) instead of the
prototype's in-memory mock cases.

To view the prototype: open `Argus Workbench.dc.html` in a browser. It is best viewed at
**≥1280px wide** (it is a three-column workbench; below ~1000px the case/live panes get
cramped — see Responsive Behavior).

## Fidelity
**High-fidelity (hifi).** Final colors, typography, spacing, and interactions are all
specified below and are intended to be reproduced closely. The one caveat: this is a
desktop analyst tool designed for wide screens — reproduce the *system* (tokens,
component anatomy, states) pixel-faithfully, and apply the documented responsive rules
rather than treating the narrow-width prototype rendering as canonical.

---

## Global Layout

```
┌──────────┬───────────────────────────────────────────────┐
│ NAV RAIL │  MAIN (one of 4 views)                         │
│ 230px    │  Overview | Case files | Live triage | Ask     │
│ fixed    │                                                │
│ sticky   │  Case files & Live triage = TWO-PANE:          │
│ full-ht  │    ┌ queue col 340px ┬ detail pane (flex) ┐    │
│          │    └ own scroll      ┴ own scroll         ┘    │
└──────────┴───────────────────────────────────────────────┘
```

- Root: `display:flex; min-height:100vh; background:#08090c`.
- **Nav rail**: `width:230px; flex:none; position:sticky; top:0; height:100vh;
  background:#0b0d11; border-right:1px solid rgba(255,255,255,.06); padding:20px 16px;
  display:flex; flex-direction:column`.
- **Main**: `flex:1; min-width:0`.
- Two-pane views set their wrapper to `display:flex; height:100vh`; each column has its
  own `overflow-y:auto`. Overview and Ask are single-column, page-scroll.

---

## Screens / Views

### 0. Nav Rail (persistent chrome)
- **Purpose**: switch views; show system status.
- **Brand**: 32×32 rounded-9px red (`#ff5245`) square with a white shield glyph
  (CSS `clip-path: polygon(50% 0,100% 22%,100% 58%,50% 100%,0 58%,0 22%)`), shadow
  `0 4px 16px rgba(255,82,69,.4)`. Wordmark "ARGUS" 700/17px, kicker "FRAUD OPS"
  mono 9.5px `#59616e` letter-spacing 1px.
- **Nav items** (Overview, Case files, Live triage, Ask Argus): full-width buttons,
  `font:600 13px`, `padding:11px 12px`, icon (18px, stroke `currentColor`) + label.
  - Active: text `#eef1f6`, background `rgba(255,82,69,.1)`, `border-left:2px solid #ff5245`,
    `border-radius:0 8px 8px 0`.
  - Inactive: text `#8a929e`, transparent, `border-left:2px solid transparent`.
  - Icons: Overview = 2×2 rounded rects (grid); Case files = document w/ 3 lines;
    Live triage = ring + center dot; Ask = speech bubble.
- **SYSTEM panel** (mono 9.5px label `#59616e`): status dot + word — `idle` (`#8a929e`,
  hollow dot), `running` (`#f4b13c`, pulsing dot), `done` (`#37d68a`, filled dot);
  reflects the live-pipeline state. Benchmark bar "51/80" = 5px track
  `rgba(255,255,255,.08)`, fill 64% width `#ff5245`. Meta lines: "80 cases on disk",
  "model · claude-sonnet-5", "critic · claude-opus-4".
- **User chip** (bottom, `margin-top:auto`): 30px round avatar `#1d3352`/`#8fc0ff`
  initials "AR", name "A. Reyes", role "Senior analyst".

### 1. Overview
- **Purpose**: explain the system + show benchmark results.
- **Header**: title "Overview" (700/19px) + mono subtitle; right-aligned red primary
  button "▶ Run live triage" (navigates to Live triage).
- **Metric strip**: 4 equal cards (`repeat(4,1fr)`, gap 14px). Card =
  `bg:#101319; border:1px solid rgba(255,255,255,.07); radius:14px; padding:18px 20px;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.03)`. Label 12px `#8a929e`, big number
  600/32px letter-spacing -.5px, sub 11px mono. Values: **Frauds caught 25/26**
  (96% recall, green), **Faithfulness 0.88** (green), **H2H vs baseline 5/6**,
  **Queue depth 12** (amber).
- **Two columns** (`1.15fr 1fr`): left = "What Argus does" prose card + pipeline
  breadcrumb (`Alert › Orchestrator › Retriever › Analyzer › Policy › Critic › Human gate`,
  last node red `#ff8078`); right = benchmark table (baseline vs Argus full) with columns
  SYSTEM / P / R / F1, Argus row tinted green `rgba(55,214,138,.05)` with green figures.
- **Agent roster**: mono label "THE AGENTS", 3-col grid of cards; each has a colored
  4px square + name + description. Agent accent colors: Orchestrator/Retriever `#6ea2ff`,
  Analyzer/Policy `#f4b13c`, Critic `#ff5245`, Assembler+Gate `#37d68a`.

### 2. Case files (TWO-PANE — the primary view)
- **Purpose**: browse investigated cases and read the full investigation report.

**Queue column (340px):**
- Header "Investigated cases" (700/16px) + "80 on disk · 6 shown".
- **Filter chips**: All / Escalated / Cleared. Active chip `bg:#1d222b`, border
  `rgba(255,255,255,.18)`, text `#eef1f6`; inactive transparent/`#8a929e`.
- **Case rows** (selectable buttons): `bg:#0d1015` (selected `#141922`), border
  `rgba(255,255,255,.06)` (selected `rgba(255,82,69,.35)`), radius 12px, margin-bottom 9px.
  Row content: `txn <id>` (mono 600/13) + a REC badge (ESCALATE = `rgba(255,82,69,.15)`/
  `#ff8078`; CLEAR = `rgba(55,214,138,.14)`/`#6fe0ac`) + right-aligned **risk % in risk
  color**; second line `<TYPE> · <amount>`; a 4px **risk meter** (width = risk%, color by
  band); footer `truth: <fraud|legit>` + status pill (PENDING `#59616e` / ESCALATED
  `#ff8078` / CLEARED `#6fe0ac`).

**Detail pane (flex, own scroll):** report for the selected case, max-width 940px,
padding `26px 34px 70px`. Sections top-to-bottom:
- **Header row**: "Case <id>" (700/24px) + REC badge; sub line
  "Ground truth · <actually fraud|legitimate> — Argus was correct · status PENDING_APPROVAL".
  Right: **risk gauge card** (min-width 210px) — "MODEL RISK" + band (HIGH/ELEVATED/LOW),
  big risk number in risk color (600/30px), "conf 0.xx", and a 5px meter.
- **Agent trace strip**: horizontal, 6 nodes (Orchestrator→Case File) each a green filled
  dot + label + caption (e.g. "risk 0.94", "revised → ok"), connected by 26px hairlines;
  `overflow-x:auto`.
- **01 The alert**: sentence + 4 metric cards (Amount, Balance before, Balance after
  [delta colored], Destination). Metric value mono 600/19px.
- **02 Evidence gathered**: **Baseline chart card** (see Signature Components) FIRST, then
  a 3-col grid of key/value cards: Sender baseline, Counterparty, Velocity. Rows are
  `label … value` with a top hairline; values mono.
- **03 Money flow**: horizontal **counterparty diagram** (see Signature Components).
- **04 Risk signals**: wrap of chips; severity-colored (crit red, warn amber, ok green).
- **05 Policy rules**: table — columns RULE / FIRED / CHECK / VALUES. Fired = "● FIRED"
  red; not fired = "— clear" `#59616e`. Footer "Verdict · <ESCALATE|CLEAR> — <note>".
- **06 Critic fact-check**: **revision loop** (see Signature Components).
- **07 Decision fusion**: **Analyzer-vs-Policy agreement** row (see Signature Components)
  then reasoning rows (`key` mono `#6ea2ff` + explanation).
- **08 Your decision**: **human approval gate** (see Interactions → Approval Gate).
- **09 Audit trail**: chronological log rows — `time` mono `#6b7381`, `actor` mono
  (colored), `what`. System events (retriever/analyzer/policy/critic/assembler) are
  pre-seeded; the human decision appends a row with the typed rationale.

### 3. Live triage (TWO-PANE)
- **Purpose**: run the full pipeline live on a queued alert, then decide.
- **Queue column (340px)**: "Alert queue" + rows (`txn`, risk dot, known-fraud/legit tag,
  `<TYPE> <amount>`). Bottom: full-width red **Investigate alert** button (label →
  "Investigating…" with ◐ while running, → "Re-run" when done; disabled+dimmed while running).
- **Run pane**:
  - *Idle state*: centered empty-state (ring icon, "Ready to investigate", helper text).
  - *Running*: title "Investigating txn <id>", then a **vertical agent timeline** — 6 nodes,
    each a dot + connective line + label + a mono log line. Node states pending
    (hollow) → active (red, pulsing) → done (green); log fills in per step.
  - *Done*: reveal a compact report (recommendation banner, 4 alert cards, signal chips,
    critic passes) followed by the **same approval gate** as Case files (keyed to the
    queued case).

### 4. Ask Argus
- **Purpose**: grounded Q&A about one investigated case.
- **Header** + case chips (right) to pick which case you're asking about.
- **Suggested questions**: 3 cards ("Why was this alert escalated (or cleared)?",
  "What did the Critic verify before approving?", "Explain this case to a non-technical
  manager in 3 sentences.").
- **Thread**: user bubble (right, `#1d3352`/`#cfe4ff`) + Argus answer (left, shield avatar,
  `#101319` card). Answers are **grounded in that case's record**; if the question isn't
  answerable from the record the assistant says so instead of guessing.
- **Composer**: sticky input + red "Ask" button (Enter submits).

---

## Signature Components (build these carefully — they're the point of the redesign)

### A. Baseline chart ("Amount vs this account's own history")
Bar strip proving how anomalous the alert is.
- Card `bg:#101319`, header "Amount vs this account's own history" + right-aligned
  "**<N>× typical**" in risk color.
- Chart: `position:relative; height:64px; display:flex; align-items:flex-end; gap:3px`.
  15 baseline bars `rgba(255,255,255,.13)`, heights ∝ each prior amount (normalize by
  `max(history, alertAmount, typical)`), each `flex:1; min-width:3px; radius:2px 2px 0 0`.
- The **alert bar** is appended last: same sizing but `background:<riskColor>` and a glow
  `box-shadow:0 0 12px rgba(255,82,69,.55)` (amber glow if band is elevated).
- A **dashed "typical" reference line**: absolutely-positioned full-width
  `border-top:1px dashed rgba(255,255,255,.26)` at `bottom = round(typical/max*56)px`.
- Footer legend + a plain-English note whose wording depends on multiplier & recommendation
  (e.g. "This transaction is 92× larger than anything this account normally sends — a
  classic balance-drain signature." vs the legit-but-large explanation).

### B. Money-flow diagram (counterparty)
Horizontal `Sender → (amount) → Destination → (cash-out)`, `overflow-x:auto`, min-width 600px.
- **Sender node** (150px): `bg:#0c0e13`, "Sender" + masked account + "flagged account".
- **Connector**: amount pill (`#14181f` chip) over a 2px gradient line
  (`rgba(255,255,255,.06) → destColor`) + "<type> ▶" caption in dest color.
- **Destination node** (184px), colored by kind:
  - `mule` → red `#ff5245`, badge "PASS-THRU", bg `rgba(255,82,69,.07)`;
  - `merchant` → green `#37d68a`, badge "VERIFIED";
  - `internal` → blue `#6ea2ff`, badge "HOLDS BAL".
  Contains label + masked account + a **fan-in row** (6 small dots + "×<N> in") + a note
  ("0.94 of inflow passes straight through — textbook mule", etc.).
- **Cash-out node** (only if `isCashOut`): red card "Cash-out / funds exit the system —
  unrecoverable", preceded by a red gradient connector "cash ▶".

### C. Critic revision loop
Vertical stack of "passes". Each pass = a badge box (24px, border in pass color) + title
"Pass <n> · <flagged — sent back for revision | approved>" + body text.
- Flagged pass: amber `#f4b13c`, bg `rgba(244,177,60,.07)`, badge "⚠", body describes the
  specific claim the Critic rejected (e.g. "Analyzer claimed '12 outgoing transfers'…
  evidence shows 6 — sent back for revision").
- Approved pass: green `#37d68a`, bg `rgba(55,214,138,.06)`, badge "✓".
- Cases where the Critic caught something have 2 passes (flag → approve); clean cases have 1.

### D. Analyzer-vs-Policy agreement
Row of: **Analyzer · LLM** chip ("FLAGS FRAUD" if risk ≥ 0.5 else "READS BENIGN",
colored), **Policy · RULES** chip (ESCALATE/CLEAR, colored), then a wide status pill:
- agree → green "✓ Both agents agree";
- disagree → amber "⚠ Agents disagree — resolved by fusion rule".
(The `CLEAR` case with risk 0.55 is intentionally a *disagreement* — Analyzer leans fraud,
Policy clears — to demonstrate the fusion rule.)

---

## Interactions & Behavior

### Navigation
- Nav-rail buttons switch the active view (`overview | cases | live | ask`). Overview's
  "Run live triage" button jumps to Live triage.
- Case rows / queue rows / ask chips set the selected case for their pane.
- Filter chips (Case files) filter the queue by recommendation.

### Live pipeline animation
- Clicking **Investigate alert** runs a 6-step sequence (~900ms/step). Each node goes
  `pending → active (pulsing red) → done (green)`; a mono log line is appended when a node
  completes. The nav-rail SYSTEM status mirrors this (`idle → running → done`). When the
  last node completes: fire a toast and reveal the report + gate. **Re-run** resets and
  replays. In production, replace the timers with real streamed progress events from the
  agent pipeline.

### Approval gate (the weighted human-in-the-loop step) — sections 08 & Live
State machine per case: **buttons → composer → decided** (with Undo back to buttons).
1. **Buttons state**: "✓ Dismiss alert" (green outline) + "▲ Approve escalation" (red).
   Labels adapt to the recommendation (on a CLEAR case: "Override → escalate" /
   "Confirm clear").
2. Clicking either opens the **rationale composer**: a prompt ("Confirm escalation — this
   freezes txn <id>"), a **required textarea** (min 8 chars), a live char counter
   ("<n> / 8 min chars", green when satisfied), **Cancel** + a **Confirm** button that is
   disabled/greyed until the rationale is long enough (Confirm is red for approve, green
   for dismiss).
3. **Confirm** commits: writes a decision + an **audit entry** (timestamp, actor "A. Reyes",
   action, rationale), fires a toast ("Escalation approved · logged to audit trail"), flips
   the queue-row status pill (PENDING → ESCALATED/CLEARED), and shows the **decided state**
   (logged decision with the rationale quote, timestamp, and an **Undo** that reverts the
   decision and removes the last audit entry).
- **Guardrail**: nothing is "frozen/cleared" without an explicit confirm + rationale — this
  is the product's core safety property (mirror the backend's human gate in
  `argus_backend_spec.md §8`). All actions are simulated in the prototype.

### Ask Argus
- Suggested-question cards and the input both submit to a grounded answer function keyed by
  the selected case. Enter submits. Answers must only use that case's evidence/audit trail;
  otherwise reply that the detail isn't in the record.

### Toasts
- Bottom-right, `#14181f`, left border in the action color, auto-dismiss ~4.2s. Used for
  decisions and "Investigation complete".

### Animations & timing
- `fadeUp` 0.25–0.35s ease on view/report reveal. Node pulse ~1.1s. Blink ~1s for the
  live cursor / queue indicator. Keep easing subtle; this is a serious tool.

---

## State Management
Prototype state (recreate as component state / a store):
- `tab`: active view.
- `caseId`, `queueId`, `askCaseId`: selected case per pane.
- `caseFilter`: `all | escalate | clear`.
- `live`: `{ started, running, done, nodes[6] (pending|active|done), log[] }`.
- `decisions`: `{ [caseId]: 'approved' | 'dismissed' }`.
- `audit`: `{ [caseId]: [{ ts, action, rationale }] }`.
- `pendingAction`: `{ caseId, action } | null` (which gate composer is open).
- `rationaleText`: current textarea value (gate).
- `threads`: `{ [caseId]: [{ q, a }] }` (Ask).
- `toast`: `{ title, body, color } | null`.

**Data fetching (production):** replace the in-memory case list with the backend's
investigated case files (per `argus_backend_spec §6, §11`); each case supplies alert,
evidence bundle, signals, policy rows, critic passes, reasoning, ground-truth label. The
live pipeline should stream real agent/tool events. The audit trail should read/write the
backend's per-case audit object (`§9`).

---

## Design Tokens

**Color**
| Token | Hex | Use |
|---|---|---|
| bg | `#08090c` | app background |
| rail | `#0b0d11` | nav rail |
| surface | `#101319` | cards |
| surface-2 | `#14181f` | table headers, chips, toast |
| surface-inset | `#0c0e13` | insets, audit list, textarea |
| row-idle | `#0d1015` | queue rows |
| row-sel | `#141922` | selected row |
| line | `rgba(255,255,255,.06–.09)` | hairlines/borders |
| ink | `#eef1f6` | primary text |
| ink-2 | `#aab2bf` | secondary text |
| muted | `#8a929e` | tertiary |
| faint | `#6b7381` / `#59616e` | mono labels, captions |
| **red (accent/fraud)** | `#ff5245` | primary action, escalate, critical |
| red-soft | `#ff8078` | red text on dark |
| **green (clear/ok)** | `#37d68a` / `#6fe0ac` | clear, approved, benign |
| **amber (warn)** | `#f4b13c` / `#f4c46a` | warnings, running, disagreement |
| blue (info) | `#6ea2ff` | orchestrator/retriever, internal accounts, reasoning keys |
| avatar | `#1d3352` bg / `#8fc0ff` fg | user & chat |

Risk color by band: `≥0.7 → #ff5245 (HIGH)`, `0.4–0.7 → #f4b13c (ELEVATED)`,
`<0.4 → #37d68a (LOW)`.

**Typography** — two families:
- **IBM Plex Sans** (400/500/600/700): all UI text & headings.
- **IBM Plex Mono** (400/500/600): all data, numbers, ids, amounts, labels/kickers, logs.
- Big numbers: 600/30–32px, letter-spacing -.5px. Section titles 600/17px. Mono kickers
  ~9.5–11px, letter-spacing .5–1.1px, uppercase.

**Radius**: 8px (chips/buttons), 10–12px (cards/rows), 13–14px (large cards/gauges),
`0 8px 8px 0` (active nav item).

**Spacing**: section blocks `margin:30px 0 13px`; card padding 14–22px; grid gaps 11–14px;
pane padding `26px 34px`.

**Shadow**: card inset highlight `inset 0 1px 0 rgba(255,255,255,.03)`; primary button
`0 5px 16px rgba(255,82,69,.3)`; toast `0 14px 44px rgba(0,0,0,.55)`; node pulse
`0 0 0 4px rgba(255,82,69,.2)`.

---

## Responsive Behavior
Desktop-first analyst tool. Target ≥1280px.
- Nav rail fixed 230px. Two-pane queue column fixed 340px; detail/run pane is fluid with
  its own scroll.
- Money-flow diagram and agent-trace strip use `overflow-x:auto` (min-width 600px) so they
  scroll rather than squash on narrow panes.
- Below ~1000px, consider collapsing the queue column into a top dropdown/list and stacking
  the two panes. The prototype does not implement a mobile layout — this is a workstation UI.

## Assets
- **Fonts**: IBM Plex Sans + IBM Plex Mono (Google Fonts). Swap to the app's licensed
  copies if available.
- **Icons**: 4 inline SVGs (grid, document, target ring, speech bubble), stroke
  `currentColor`, 18px — replace with the codebase's icon set.
- **Logo/shield**: pure-CSS `clip-path` shield on a red square — replace with the real
  Argus mark if one exists. No raster assets, no third-party imagery.
- If your codebase has an established design system / brand, prefer its tokens and
  components over these literals; keep the red/green/amber semantic mapping.

## Files
- `Argus Workbench.dc.html` — the interactive design reference (all 4 views + signature
  components + gate/audit flow). Open in a browser to interact.
- `argus_backend_spec.md` — the backend/agent/data/eval spec this UI sits on top of.
- `IMPLEMENTATION_CHECKLIST.md` — phased, checkable build order for a Claude Code session.
- `README.md` — this document (self-sufficient).
- `screenshots/` — annotated reference renders (see index below).

## Screenshots (in `screenshots/`)
1. `01-overview.png` — Overview: metric strip, benchmark table, agent roster.
2. `02-case-files-two-pane.png` — Case files: queue column + detail header, risk gauge, agent trace.
3. `03-evidence-baseline-chart.png` — §02 baseline chart ("92× typical" spike) + evidence cards.
4. `04-money-flow-diagram.png` — §03 counterparty money-flow (Sender → amount → Mule → cash-out).
5. `05-critic-loop-and-agreement.png` — §06 Critic revision loop (flagged → approved) + §07 agreement panel.
6. `06-decision-gate-logged.png` — §08 approval gate, decided state with logged rationale + Undo.
7. `07-audit-trail.png` — §09 audit trail incl. the human decision row.
8. `08-live-pipeline-running.png` — Live triage: vertical agent pipeline mid-run.
9. `09-live-report-critic.png` — Live triage: revealed report + critic passes.
10. `10-live-approval-gate.png` — Live triage: approval gate.
11. `11-ask-argus.png` — Ask Argus: grounded Q&A thread.

Note: screenshots were captured in a narrow preview; the money-flow and agent-trace strips
scroll horizontally and appear clipped on the right — see the live prototype for the full width.
