# docs/proposals/

Pre-launch strategy and business documents — grant applications, monetization
strategy, competitive positioning, and product proposals. These are internal
planning material, not user-facing documentation and not regulatory-grade
technical content: nothing here should be read as a commitment, a published
claim, or a technical specification.

| File | What it is |
|---|---|
| `pyvar-grant-brief.docx` | General-purpose grant brief, adaptable to any funder. |
| `pyvar-grant-brief-nlnet.docx` | The same brief adapted for NLnet Foundation. Fund name resolved to **Restack** (deadline 2026-11-03) — see its "before you submit" note. This is source material, not the actual submission artifact: the real form is short-form (see `nlnet-restack-form-answers.md`). |
| `nlnet-restack-form-answers.md` | Draft condensed answers to NLnet's actual `nlnet.nl/propose/` web form, for the Restack fund. Only 3 of 6 questions confirmed this session — Filippo needs to verify the rest against the live form before submitting. |
| `pyvar-monetization-strategy.docx` | Open-core/support sustainability model — how pyvar funds its own infrastructure without narrowing the Apache-2.0 licence. |
| `pyvar-iron-triangle-benchmark.docx` | Cost/speed/accuracy positioning vs. traditional risk vendors. Directional and explicitly caveated — not an audited benchmark. |
| `pyvar-local-package-proposal.docx` | Design proposal for a downloadable, offline-capable "pyvar Local" package. See `docs/p11-pre-launch-hardening.md` §2 for the implementation plan built on top of this. |
| `marketplace-submission-content.md` | Prepared content for submitting pyvar's plugin marketplace to Anthropic's official Claude Code plugin directory (the whole `pyvar-marketplace` bundle). |
| `marketplace-submission-content-per-plugin.md` | The same, broken out per individual plugin (13 skills + `pyvar-mcp`), in case the submission mechanism turns out to want one entry per plugin rather than one for the bundle. |
| `smithery-submission-content.md` | Draft submission content for `pyvar-mcp` to Smithery (smithery.ai), an alternative MCP registry — prepared while the `claude-plugins-community` submission is still pending review. |

See `docs/p11-pre-launch-hardening.md` for how these tie into the pre-launch
implementation plan.
