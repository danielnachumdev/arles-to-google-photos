---
name: Feature request
about: Scannable planning ticket for new work (outcome-focused, not a design dump)
title: ""
labels: enhancement
assignees: ""
---

## **Background (Context)**

<!-- Planning ticket for humans and agents—not a full spec. Aim for ~2 minutes to read.
     Keep product-specific paths and API shapes out unless this ticket is a design spike. -->

One short paragraph for follow-ups (link `#issue`); one to two max for standalone work. State the current gap vs desired outcome. Skip architecture recaps already in `AGENTS.md` / `README.md`.

…

## **Motivation (Why)**

Lead with the strongest reason this matters for **operators, users, or maintainers** (ops pain, reliability, UX, unblock). Two to four bullets; do not repeat Requirements or AC.

…

## **What Needs to be done? (Requirements)**

Numbered steps when order matters (`1.`, `2.`, …)—one sentence each. Prefer product outcomes over file paths and API shapes unless this ticket is explicitly a design spike.

Shapes:

- **Fix** — 1–2 steps (fix + verify)
- **Deliver** — known work, 1–3 steps
- **Discover → decide → build** — research / sign-off only when the approach is unclear

Optional at end: **Out of scope:** …

…

## **How Do We Know We Are Done? (Acceptance Criteria)**

Three to six checkboxes; one verifiable outcome each (CLI / API / UI, tests, docs). Do not copy Requirements verbatim.

- [ ] …
- [ ] Docs updated if operator- or user-facing
- [ ] Tests at the right layer for the change

---

<details>
<summary><strong>Examples (delete before submitting)</strong></summary>

**Deliver** — Background: current vs desired. Motivation: why now. Requirements: 2–3 deliver steps; inline out-of-scope. AC: observable behavior.

**Follow-up** — Background: link prior `#issue` in one paragraph. Requirements: only the remaining slice. AC: that slice verified.

**Discover → decide → build** — Background: unknown approach. Requirements: research + lock a decision, then implement. AC: decision recorded; agreed slice shipped.

</details>
