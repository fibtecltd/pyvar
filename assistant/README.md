# assistant/: the portal assistant

The prompts, graders and model plumbing of the portal's menu assistant. The eval harness
(`scripts/assistant_eval/`) measured these modules; production imports them from here, so what ships is what was
measured. Design and numbers: `docs/assistant-plan-implementation.md`, `docs/assistant-phase0-results.md`.

| Module | Role |
|---|---|
| `prompts.py` | system prompt, per-action tasks, `build_request` (PROMPT_VERSION `v4-2026-11-09`) |
| `graders.py` | programmatic graders: identifiers, numbers, advice, wording, length (`grade`, `grade_prose`, `grade_typed`, `oracle_text`) |
| `gate.py` | the model gate: `gate(client, case, text) -> Verdict` (faithful, issues, cost); `JUDGE_SYSTEM`, `judge_message`, `parse_verdict` |
| `static_text.py` | the static answer built from the record: the floor under every bank entry |
| `client.py` | `ModelClient` protocol and `AnthropicClient`; the **only** module that imports `anthropic` (inside the constructor) |
| `tools.py` | the typed agent's three read-only tools and the `ToolBox` that remembers what they returned; `hit_view` is what a search hit shows |
| `typed_prompts.py` | the typed system prompt (`t2-2026-11-12`, same words as the first typed run) and `build_typed_request` |
| `typed_graders.py` | `grade_typed` with the stock-decline and quoting-refusal false positives fixed; wraps `graders.grade_typed`, which cannot change (the bank pins its hash) |
| `bank.py` | `python -m assistant.bank build\|check`: writes and checks the answer bank |
| `cost.py`, `records.py`, `body_schema.py`, `scrub.py` | token prices and cost, `trim_record`, request-body checker, secret scrubber |

## The answer bank

Every menu answer (explain, when, compare: 1,154 for 385 functions) is written ahead of time and served as a
static file, so no model is called when a visitor clicks. Layout:

```
portal/assistant/bank/manifest.json                 bank_version, prompt_version, prompt_sha256, grader_sha256,
                                                    catalogue_sha256, models, built, counts, complete, stopped
portal/assistant/bank/<bank_version>/<function>.json  {"explain": entry, "when": entry, "compare": {<sibling>: entry}}
entry = {text, source: "model"|"static", writer, tries, escalated, gate: {faithful, issues}, record_sha256}
bank_version = <prompt_version>-<first 8 of catalogue_sha256>
```

Pipeline per answer (measured in run C, results 9.19): the writer (`assistant_writer_model`, Sonnet 5.5) writes; the
graders check; a failure sends the failing checks back, up to 3 writer calls; the gate (`assistant_gate_model`,
Opus 5.5) reads the text; a gate flag is rewritten once by `assistant_escalation_model` (Opus) with the gate's
issues as feedback, graded and gated again; whatever still fails becomes static text (`source: "static"`).

```bash
# Build (paid; needs ANTHROPIC_API_KEY in the environment or .env, and `pip install -r scripts/assistant_eval/requirements.txt`)
python -m assistant.bank build --max-usd 20 --workers 4          # all functions, resumable, never exceeds the cap
python -m assistant.bank build --max-usd 2 --only-functions liquidity_coverage_ratio_lcr,retail_deposit_runoff_rate
python -m assistant.bank build --max-usd 2 --retry-static        # try again the answers that fell back to static
python -m assistant.bank build --max-usd 3 --redo-ids docs/assistant-bank-redo-1.json
# --redo-ids: {"function:action[:sibling]": ["note", ...]}. Rewrites those answers once, in place: the writer is
# shown its old answer and the notes, then graders, gate and escalation run as usual. Never makes an answer
# worse: a rewrite that would be static text, a failed call or a budget stop keeps the old entry.
# Check (no API, no key): manifest and per-answer hashes against the live catalogue, every answer re-graded,
# size bounds, static share under 3%. Exit code 1 on any problem.
python -m assistant.bank check
```

A build is incremental (an entry is kept when its record hash, the prompt version and the grader hash are
unchanged, taken from the previous version's directory or from an interrupted run of the same version), resumable,
atomic per file, and the money cap is hard: the worst case of each call is reserved first, so the build stops
before exceeding `--max-usd` and records `complete: false`. A full build costs about $15 (run C estimate).

**Never edit a bank file by hand.** The bank is rebuilt by the CLI; CLAUDE.md section 3.6 has the rules.

## Serving and the widget

`/public/config` reports `assistant_enabled` (the setting `assistant_enabled` AND a complete manifest) and
`assistant_bank_version`; `/assistant/bank/` serves the files with `Cache-Control: public, max-age=3600`
(`api/assistant_bank.py`). `portal/assistant.js` loads only when enabled, fills the Try-it panel's slot, reads one
small file per function, sends nothing, and hides itself on any failure.

## Tests

`tests/test_assistant_core.py` (kernel unchanged, egress rule), `test_assistant_client.py`, `test_assistant_bank.py`
(fake clients only; the drift tests on a committed bank skip while `manifest.json` is absent),
`test_assistant_api.py`, `test_assistant_widget.py`, `test_assistant_graders_line_start.py`.
No test needs a key or the network.
