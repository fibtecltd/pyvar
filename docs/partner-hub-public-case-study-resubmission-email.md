# Draft: Public Case Study resubmission reply (Claude Partner Network)

**Status:** Ready to send — reply to Anthropic Partner Support's decline of the
original Customer Story submission for pyvar.com.

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
