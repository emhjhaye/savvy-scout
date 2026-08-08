# Trifork UK Scouting — End-to-End Process (Phase 1 to Capture)

**Purpose:** the repeatable pipeline that turns a screen of raw UK public-sector notices into decision-ready opportunities for Victoria. Every step names its input, its decision, its output, and who owns the call. The specific clicks are a means; the outcome is the job — nothing viable missed, no one's time wasted, every shortlisted opportunity decision-ready.

**Use alongside:** the Capability Reference (capability areas, key products, known gaps), the Tracker Quick Key (column meanings), and the confirmed sector scope. This document is the *flow*; those are the *lookups*.

---

## The pipeline at a glance

| Step | Name | Input | Output | Who decides |
|---|---|---|---|---|
| 0 | Signal capture | Portal sweep | Raw candidate list | You |
| 1 | **Phase 1 — Bulk scan** | Raw list | Eliminated / Kept split | You |
| 2 | **Phase 2 — Gate triage** | Kept list | PASS / FAIL / FLAG + tracker rows | You (fail/flag); Victoria (flag calls) |
| 3 | Deep verification & qualification | Each PASS/FLAG | Verified facts, HIGH/MED/LOW rating | You |
| 4 | Capture brief + internal addendum | Qualified opportunity | The two artifacts | You draft; Victoria reviews |
| 5 | Reviewer decision & close-out | Brief + addendum | Bid / no-bid, logged | Victoria |

Maps to Kanvesh's tracker phases: Step 1 = his Phase 1 quick scan; Step 2 + 3 = his Phase 2 (open each PASS) and Phase 3 (qualification); Step 4 = his Phase 4 capture; Step 5 = his reviewer decision.

---

## Step 0 — Signal capture

**Sources:** Find a Tender (primary, higher-value), Contracts Finder (England sub-threshold), Scotland/Wales portals if full coverage is needed. Automate later via the Find a Tender OCDS API.

**Sectors in scope (confirmed verbally by Victoria — overrides older written lists):** Fintech · Aviation (airlines only, NOT airports) · Rail & Transport · Energy.

**Route elsewhere, don't scout:** airport-side notices → Maddy; rail notices of unclear ownership → coordinate with Kanvesh (known patch overlap), don't auto-fail or auto-route. No secondary sectors until Kanvesh confirms.

**Output:** a raw candidate list with the source link for each. No judgement yet.

---

## Step 1 — Phase 1: Bulk scan

**One line:** eliminate only the obvious fails; keep everything doubtful.

Fast pass on title and description only. Phase 1 errs toward coverage — a wrongly kept notice costs a Phase 2 look; a wrongly killed one is lost silently.

**Eliminate only when obviously:**
- **Out of sector** — buyer/domain isn't one of the four (airports included here as out).
- **Hardware / works / construction** — core deliverable is kit, infrastructure, or building, not software. (The disguised-hardware trap: tech language wrapping a physical buy.)
- **Clearly dead-stage** — already awarded, closed, or sole-sourced to a named incumbent.

**Keep everything else**, including anything ambiguous on sector or capability.

**Output — the Phase 1 table:**

| Notice (ref) | Sector | Verdict | Deciding reason | Relation to capability |
|---|---|---|---|---|

Verdict is **Kept** or **Eliminated**. Flag eliminated-on-stage-only notices (dead now, in-scope domain) as watch-list rather than bin.

---

## Step 2 — Phase 2: Gate triage

**One line:** run each Kept notice through seven gates, cheapest/most-decisive first, for one verdict.

Open the full notice. Test in order — a fail on an early gate can end the run.

1. **Sector fit** — one of the four? Out → FAIL; ambiguous → FLAG.
2. **Actionable stage** — open tender = live; awarded = dead (FAIL); planning/early-engagement is NOT a fail, it's a pre-engagement brief.
3. **Capability match** — does the *real* requirement map to a capability area or key product? A product match (Corax, Tiris, Erlang/Elixir engineering) beats generic keyword language ("AI", "data", "platform").
4. **Value fit** — UNASSESSABLE until Victoria confirms a £ band with a date. Note value for reference; never pass/fail on it. Mark "pending threshold."
5. **Deadline feasibility** — UNASSESSABLE until Victoria confirms minimum lead-time. Never fail on it. Mark "pending threshold."
6. **Eligibility / structural barriers** — a binary requirement Trifork cannot meet (accreditation, closed-framework call-off Trifork isn't on, clearance, SME-only) = **hard FAIL you decide**. A capability gap (could do it, lacks a proof point) = **FLAG for Victoria**. Same-looking, opposite handling.
7. **Strategic / win value** — winnable or worth a reference? Priority signal only, never a fail.

**Sub-checks that feed the gates (not separate gates):**
- **CPV codes** — match against the verified/inferred list. Not in any list → flag under Gate 1 or 3, don't rate capability. Label Verified vs Inferred.
- **Framework status** — Direct Procurement or Framework Entry Bid = proceed. Call-off from a framework Trifork isn't on = FAIL under Gate 6.

**Output — the Phase 2 table** (one column per notice, one row per gate, then VERDICT and tracker action). Every carried-forward row shows Gates 4 and 5 as "pending" until thresholds land — never silently omit them.

End every triage with: **"Agree or disagree?"**

---

## Step 3 — Deep verification & qualification

**One line:** confirm the facts from the primary legal notices, resolve every open flag, assign a capability rating.

Only for PASS and FLAG rows. Pull the full notice and bid pack. Confirm — from the legal notice, not the summary page — the real CPV codes, real value, framework status (direct / entry / call-off), and stage. Check the filters properly rather than leaving them flagged.

**Resolve open flags.** Anything marked CONFIRM or UNRESOLVED needs a real answer before it can move to capture. Do not let a flagged row drift into a brief unresolved — name the actual open question and route it to the reviewer or to Trifork via Victoria.

**Assign capability fit:** HIGH (a real product/service matches directly) · MED (plausible, needs a stretch) · LOW (no clear match). Check the known capability gaps before any HIGH/MED: no confirmed UK security clearance, no UK central-gov references, no UK framework access as of June 2026, ~15 staff / £3m turnover scale limit.

**Output:** a fully verified tracker row, every fact source-tagged, capability rated, flags resolved or explicitly escalated.

---

## Step 4 — Capture brief + internal addendum

**One line:** package a HIGH (or reviewer-approved MED) opportunity into the two artifacts, sourcing every fact from the verified notice.

**Artifact 1 — Client Capture Brief** (client-facing, Confidential):
executive summary + status callout, glossary, how the procurement regime fits, timetable & status (source-tagged fact table), selection categories & Trifork fit, places/competition, apply-now-vs-wait framework, what Trifork must do, solo-or-partner, summary decision pack, sources & confidence.

**Artifact 2 — Internal Addendum** (Not for client circulation):
the Phase 2 gate table (PASS/FAIL/FLAG + basis), process/status/owner/blocker table, blockers, direct asks for Trifork, and the single decision requested from Victoria. Does not repeat the brief — references it by section.

Handle linked opportunities as a cluster — each gets its own brief/addendum pair, cross-referenced.

**Evidence standard:** every date, value, and CPV source-attributed to a primary legal notice. Unknowns written as "confirm with Trifork / CCS", never estimated. Credential columns excluded from any output.

**Output:** the brief + addendum pair, decision-ready.

---

## Step 5 — Reviewer decision & audit close-out

Victoria makes the bid / no-bid call. All client-facing communication routes through her, not you or Claude.

**Close the loop:** record the verdict and reason on the tracker. Every dropped notice keeps a logged reason so nothing is silently lost — that audit trail is part of the deliverable, not overhead.

---

## Decision rights

- **You decide:** Phase 1 eliminations; structural fails on clear evidence.
- **You flag, don't decide:** capability gaps and genuine judgement calls.
- **Victoria decides:** bid / no-bid on shortlisted opportunities; all thresholds.
- **Kanvesh:** owner of the current process and source of truth for the scouting skill; coordination point for the rail patch overlap.

All triage verdicts are human-overridable. Claude recommends; the reviewer decides.

---

## Non-negotiables

- No value threshold unless Victoria has explicitly confirmed one, with a date.
- Never invent a figure, contact, deadline, or fact — mark UNVERIFIED.
- Never rate capability on an undocumented CPV code or scenario — flag and stop.
- Distinguish verified facts from inferred assessments, labelled clearly.
- Never fail if unsure. Fail only the obvious; ambiguous goes to the reviewer as a Flag.
- Gates 4 and 5 stay visible as "pending" on every carried-forward notice until thresholds are confirmed.
- Framework access is binary — a call-off from a framework Trifork isn't on is blocked regardless of fit.
- UK English. No em dashes. No AI filler phrases.

---

## Output formats (map to tracker columns)

**Tracker row:** REF # | DATE SPOTTED | OPPORTUNITY TITLE | BUYER | BUYER TYPE | SECTOR | SOURCE | NOTICE TYPE | INDICATIVE VALUE | CPV CODES | DEADLINE | TRIAGE STATUS | CAPABILITY FIT | FRAMEWORK STATUS | FILTER FLAGS | REASON/NOTES | NEXT ACTION | NEXT ACTION DATE | OPEN FLAGS FOR REVIEWER

**Triage status key:** PASS (pursue) · FLAG (reviewer decision needed) · PASS TO [person] (wrong patch) · FAIL (out of scope/category).

**Teams updates:** bullet-list format, not markdown tables.
