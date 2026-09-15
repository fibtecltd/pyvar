# Draft: Public Case Study resubmission reply (Claude Partner Network)

**Status:** Sent, and reassessed — **declined again, 2026-09-15** (see
"Outcome" section at the end). This path is now considered structurally
closed until pyvar has a real named joint-customer deployment; not a
process bug worth a third resubmission attempt.

**Context:** The first submission (via the Partner Hub's "Customer Stories"
form, before Anthropic's own follow-up pointed us to the Public Case Study
option) was declined for three reasons: the pages linked (`www.pyvar.com` and
the GitHub repo) didn't name Claude explicitly enough, didn't state a
measurable result, and — per the decline — "the customer is not named;
anonymous stories cannot count as public references." Anthropic Partner
Support (Fin) subsequently confirmed "Customer Stories" is the correct
submission path for a Public Case Study — it isn't a separate sidebar entry,
just the same form used when there's no named third-party customer.

This reply reframes the roles explicitly (Fibtec = Partner, Claude Code =
Product, the open pyvar.com community = Client), points at all three public
references together, and states the measurable results plainly rather than
leaving them implicit in narrative.

---

**Subject:** Re: Claude Partner Network — fibtec limited: customer story outcome

Hi,

Thanks — that follow-up on the Public Case Study option answers exactly what
we were unsure about. To be precise about the roles here, since I think
that's the source of the earlier decline: Fibtec Limited is the **Partner**,
Claude Code is the **Product/technology** that built pyvar.com end-to-end,
and the **Client** is the open community pyvar.com is published for — anyone
integrating regulatory risk computation into their own work, not a single
named enterprise account. pyvar.com is Apache-2.0 and open to every possible
client by design; there isn't a discrete third-party customer to name, and
there wasn't meant to be one. That's what makes this a **Public Case Study**,
not a Customer Success Story, and I believe it's why the original submission
(made under the Customer Story form, before your team's guidance pointed us
to the right option) came back declined for a criterion — a named
third-party customer — that doesn't apply to this shape of story.

The three public references for this case study:

- **Product:** [www.pyvar.com](https://www.pyvar.com)
- **Source code:** [github.com/fibtecltd/pyvar](https://github.com/fibtecltd/pyvar)
- **Full write-up:** [How We Built a Regulatory-Grade Financial Risk Platform
  End-to-End with Claude
  Code](https://medium.com/@filippo.buchicchio/how-we-built-a-regulatory-grade-financial-risk-platform-end-to-end-with-claude-code-086eee8d2c0e)

On measurable results specifically: the Medium write-up scores pyvar against
traditional enterprise risk vendors (Bloomberg, MSCI, Murex, Moody's
Analytics) using our own Iron Triangle efficiency model — cost efficiency,
speed, and transparency/auditability, each normalised 0–1. pyvar scores a
Total Efficiency Score of 10.0/10 against 7.3/10 for traditional vendors, on
the strength of being Apache-2.0 and free to enter, a Numba JIT-parallel
Monte Carlo engine running 100k paths in 2–10 seconds, and every formula
publicly readable and cross-validated against published Basel/FRTB
references. We've been explicit in the write-up that this is a self-scored,
illustrative positioning, not an independent or audited benchmark, and that
traditional vendors bring decades of regulatory trust an Apache-2.0 project
launched this year hasn't earned yet — we didn't want the measurable claim to
overreach what it actually is. Alongside that: Claude Code's own first draft
of a Solvency II SCR formula understated required regulatory capital by
roughly 79%, caught before launch by cross-validating against QuantLib and
published worked examples — a concrete, checkable proof point of the
"auditable correctness" the Iron Triangle score is arguing for.

We'll resubmit through the Customer Stories form with these references and
framing, per your confirmation that it's the correct path for a Public Case
Study. Thanks again for the detailed reasons on the original decline, and for
clarifying the submission path.

Best,
Filippo Buchicchio
Fibtec Limited

---

## Outcome (2026-09-15)

**Declined again**, per Anthropic Partner Support's "Update: customer story
outcomes" email received 2026-09-15. Verbatim from that email:

> fibtec limited — Declined (new). Does not yet count toward CPN tier
> credit. Reason: The published story does not meet: A named third-party
> customer. Story assessed:
> https://medium.com/@filippo.buchicchio/how-we-built-a-regulatory-grade-financial-risk-platform-end-to-end-with-claude-code-086eee8d2c0e.
> Submitted 2 times; shown once.

**What this confirms, compared against the original 3-reason decline above**:
only one reason is cited this time — "a named third-party customer." The
other two original reasons (Claude not named explicitly enough on the linked
pages; no measurable result stated) are **not** repeated, meaning this
resubmission's fixes for those two evidently landed. The "community as
client" reframing argument above did **not** succeed against the third
reason — Anthropic's assessment treats "a named third-party customer" as a
literal, non-negotiable requirement, not a role a project can satisfy by
redefining who the client is.

**Conclusion — this path is structurally closed for now, not a process bug
to retry.** pyvar.com has no third-party customer to name because it
genuinely doesn't have one (Apache-2.0, open to everyone by design). A third
resubmission with a different argument is very unlikely to succeed against
an objective, literal criterion that hasn't moved once already. The honest
next step, consistent with `docs/prd-claude-partner-hub.md` §5's own
"near-term next steps" (written before this outcome was known): revisit
Partner Network standing once pyvar actually has a real joint-customer
deployment to name — not before, and not via a cleverer resubmission.

The email's own text says a reply is possible ("If you have questions or
believe an outcome is incorrect, reply to this email and we will review
it.") — left for Filippo to decide whether that's worth pursuing given the
above, rather than assumed here.
