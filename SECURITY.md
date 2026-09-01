# Security Policy

pyvar computes regulatory-grade risk metrics (VaR, ES, Greeks, stress
testing) that institutions may rely on for real risk and capital decisions.
We take security and correctness reports seriously and ask that you report
them responsibly rather than through a public GitHub issue.

## Reporting a vulnerability

**Do not open a public issue or PR for a security vulnerability.**

Email **hello@fibtec.co.uk** with:

- A description of the vulnerability and its potential impact.
- Steps to reproduce (a minimal request payload, function name, or PR
  reference is ideal).
- Whether it's a security issue (e.g. auth bypass, injection, credential
  exposure) or a **numerical correctness issue** (e.g. a risk function
  producing a materially wrong result) — see the note below on why we treat
  both as security-relevant here.

We aim to acknowledge reports within **3 business days** and to provide an
initial assessment within **10 business days**. We'll coordinate with you on
disclosure timing once a fix is available; please give us a reasonable
window to patch before any public disclosure.

## Scope

In scope:

- The API (`api/`, `main.py`), authentication/authorization
  (`api/middleware/`), and the async job pipeline (`tasks/`, `worker.py`).
- The compute engine (`engine/`) — including numerical correctness bugs in
  regulatory-grade functions (see `CLAUDE.md` §4 for the constraints these
  are held to). A wrong VaR/ES/Greek number is a real-world financial risk,
  not just a bug, so we treat these reports with the same urgency as a
  conventional security issue.
- The `pyvar-client` Python package and its release/publish pipeline.
- The AWS infrastructure defined under `pyvar-cdk/` (CDK stack
  misconfigurations, IAM over-privilege, publicly-exposed resources) — file
  as much detail as you can from what's visible in the repository; we do not
  expect you to have access to the live AWS account to report this class of
  issue.

Out of scope:

- Findings that require physical or privileged access to Fibtec's own AWS
  account, CI secrets, or internal systems.
- Denial-of-service reports based purely on volume (rate limiting is a known,
  intentionally-tuned control — see `pyvar-cdk/stacks/edge_stack.py`).
- Issues already listed as a documented `caveat` on a function in
  `portal/functions.json` or in `docs/p11-caveat-triage-plan.md` — these are
  known, intentional simplifications, not undisclosed defects. If you believe
  one of them is more serious than documented, please still tell us.

## Supported versions

pyvar.com (the hosted API) always runs the latest `master`. There is no
older "supported version" of the hosted service. The `pyvar-client` PyPI
package follows semantic versioning; security fixes are released against the
latest minor version, not backported.

## Known limitations

This project publishes its own known simplifications rather than hiding
them: see each function's `caveat` field in `portal/functions.json` (rendered
in the portal's Try-it panel) and `docs/p11-caveat-triage-plan.md` for the
full triage. These are documented trade-offs, not vulnerabilities — but if
you find one is more exploitable or more wrong than described, that's exactly
the kind of report this policy wants.
