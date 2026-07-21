# Iron Triangle — Design Extension Brief
# For: Claude Design (visual/component work) or Claude Fable (conceptual/
#      reasoning work), whichever surface you're working in
# Context: extends an existing draft already produced in a prior Claude
#          Design session — reference that draft as the visual starting
#          point, do not design from a blank page

---

## The concept (for reference — you already have a draft of this)

The Iron Triangle is fibtec's foundational efficiency model, applicable
to every service the company offers, not just pyvar.com. It measures a
process or outcome across three axes:

- **Accuracy** — how close the result is to correct/ideal
- **Time** — how long the process took
- **Cost** — what the process cost

Each axis is plotted from a shared centre point, 120° apart, forming a
triangle. **The triangle's surface area represents inefficiency** — the
smaller the area, the better the outcome. The ideal, unreachable result
is a triangle with zero area (a single point at the centre — perfect
accuracy, instant, free).

This allows two distinct uses:
1. **Comparing two processes** on equal footing, regardless of their
   absolute scale, by comparing triangle areas.
2. **Comparing an expected result to an actual result** — two triangles
   overlaid on the same axes, showing where reality diverged from
   target, and by how much (area delta).

---

## What to produce

Building on the existing draft, extend it into:

### 1. A reusable component specification
- Single-triangle state (one process/result plotted)
- Overlay/comparison state (two triangles on shared axes — e.g.
  "Expected" as a dashed/outlined triangle, "Actual" as a solid filled
  triangle, or "Process A" vs "Process B" as two distinct fills)
- A small legend/readout showing the numeric area (or a normalised
  efficiency score derived from it) alongside the visual
- Interaction states: static display, and optionally a hover/tooltip
  state showing the raw value at each vertex (not just the normalised
  position)

### 2. Visual treatment
- Use the existing pyvar palette work as the base: near-black
  backgrounds, green accent family, amber/orange as a secondary accent,
  off-white body text (see prior brief for exact hex values if needed —
  ask if you don't have them to hand)
- The triangle itself should read clearly at small sizes (this will
  likely appear as a compact widget on dashboards and "Try it" result
  panels, not just as a large hero visual)
- Vanilla SVG preferred for implementation portability — this will be
  built in plain HTML/CSS/JS (no React, no charting library dependency)
  by a separate engineering pass afterward

### 3. Data-binding contract (light technical spec, for the engineering
   handoff — doesn't need to be visually resolved, just documented)

Each axis needs a way to convert a raw metric into a normalised
"distance from ideal" position (0 = perfect, at the centre; 1 = worst
case, at the outer edge). Propose (or confirm, if the existing draft
already handles this) a sensible default normalisation approach for
each axis, understanding that the raw units differ completely between
axes (a percentage, a duration, a currency amount):

- Accuracy: e.g. `1 - (actual / target)` for a ratio-based metric, or
  a direct percentage-off-target
- Time: e.g. `(actual_time - target_time) / target_time`, clipped to
  a sensible max
- Cost: e.g. `(actual_cost - target_cost) / target_cost`, clipped to
  a sensible max

The exact formula matters less than the component accepting a
pre-normalised 0–1 value per axis, plus the raw underlying value for
display/tooltip purposes — keep the maths out of the visual component
itself if possible, so it can be reused across different fibtec
services with different metrics and normalisation rules per use case.

### 4. A pyvar-specific application example

For pyvar.com specifically, sketch how this would appear on:
- A domain page's "Try it" result panel (single triangle, one computed
  job's Time/Cost/Accuracy)
- A dashboard or homepage trust-signal section (aggregate view —
  e.g. average/typical triangle across recent jobs, or a static
  "validated accuracy" badge if per-request accuracy genuinely isn't
  measurable — a parallel engineering task is investigating exactly
  what's real vs. estimated here, so keep this example illustrative
  rather than assuming precise live data will always be available)

---

## What NOT to do

- Don't start the visual concept from scratch — build on the existing
  draft from this Design session.
- Don't assume all three metrics are always live/precise for every
  fibtec service — the component should degrade gracefully if, say,
  Cost is only available as a rough estimate rather than an exact
  figure (visually distinguish an estimated value from a precise one
  if you think that's important — your call as the design decision).
- Don't scope this as pyvar-only in the deliverable — frame it as a
  fibtec brand-level component with pyvar as the first concrete
  application, since it will be reused across future fibtec services.

---

## Output format

Whatever your normal Design session output format is (mockup, component
spec, exported assets) — the engineering handoff afterward will be a
separate Claude Code session implementing this in portal/pyvar.js and
portal/pyvar.css, so a clear visual reference plus the data-contract
notes above are the two things that matter most for that handoff to go
smoothly.
