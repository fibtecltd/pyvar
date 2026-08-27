# P8b — DNSSEC Activation at Aruba
# Used by: scripts/claude/run.sh p8b --mode seq
# Machine: any — this is an operator-driven task in Aruba's own web panel,
#   not an autonomous coding session. The agent has no API/CLI access to
#   Aruba's account and cannot click through their UI. The agent's role is
#   precondition verification, live monitoring during/after activation,
#   and independent validation — not performing the click itself.
# Prerequisite: DNS fully settled — no other DNS record change in flight
#   or made in roughly the last 24 hours (last confirmed-clean full DNS/
#   SSL state: 2026-07-30, see docs/p8-task7-dns-ssl-verification.md).
#   Re-run Step 0 fresh before doing anything — do not trust this
#   document's cached findings as still current by the time it's used.

This task has already been investigated in full and reviewed in principle
by the operator (deferred multiple times since P4, revisited deliberately
once DNS reached a quiet, fully-settled window — see "Why this was
deferred" below). That is NOT blanket authorization to act live. Confirm
with the operator before EVERY step below that touches Aruba's panel or
changes the live DNS/DNSSEC state — not just once at the start. This is
the same standing rule applied to every DNS change this session (Route53,
Aruba, ACM validation records, CloudFront alternate domain names): each
live action gets its own fresh go-ahead, no exceptions.

The read-only verification queries in Step 0 and the monitoring queries in
Steps 5–7 are safe DNS lookups (DNS-over-HTTPS reads against public
resolvers) and do not need per-query confirmation — but nothing that
changes state at Aruba, and no click past a confirmation screen, proceeds
without an explicit go-ahead.

The investigation below is complete. Do NOT re-derive it from scratch. Do
re-verify the specific live facts in Step 0, since they may have changed
between when this was written and when this prompt is actually run.

---

## Why this was deferred (P4 → P8)

DNSSEC activation for pyvar.com has been on the list since P4 and was
explicitly carried forward, unactioned, through P6 and P7 — see
`scripts/claude/prompts/p6-lead-prompt.md`'s "P6 carry-forward to P7"
list: *"DNSSEC activation on Aruba (tracked since P4)"*. (Note:
`scripts/claude/prompts/p8-lead-prompt.md`'s Task 7 contains a stray,
incorrect line claiming "DNSSEC was activated there" — that is wrong and
should not be trusted; the P6 carry-forward note and the live
verification in Step 0 below are the sources of truth. DNSSEC has never
actually been activated for pyvar.com.)

It kept losing to higher-priority work, and more importantly, to the lack
of a stable window — DNS was mid-flux for most of that period (Aruba's
stale forwarding-proxy fault, fixed and verified in P8 Task 7; separately
the ACM/CloudFront alternate-domain-name work). Stacking a DNSSEC change
on top of an already-unsettled DNS/cert setup would have made
root-causing any new break far harder than it needed to be.

**The status-quo risk being deferred is real but narrow, and already
substantially mitigated.** Without DNSSEC, an attacker capable of
spoofing DNS responses for pyvar.com could redirect users to a malicious
server. But every pyvar.com endpoint is HTTPS-only with a legitimately
issued certificate (ACM, plus the Aruba/Actalis cert on the forwarding
proxy — see docs/p8-task7-dns-ssl-verification.md). To exploit spoofed
DNS undetected, an attacker would ALSO need a fraudulently issued TLS
certificate for pyvar.com — browsers reject/warn on a mismatched or
unauthorized cert regardless of which DNS record led them there. That
second requirement (a fraudulent cert surviving CT-log-monitored CA
issuance) is a materially higher bar than DNS spoofing alone. This
doesn't make the gap zero-risk — cache-poisoning-then-fraudulent-cert
chains have happened in the wild — but it is the reasoning that made
deferring this correct and deliberate, session after session, rather than
an oversight.

**Lower-effort partial alternative, worth checking before doing anything
here:** HSTS preloading closes a narrower but related gap — the brief
window on a user's very first-ever visit where the initial request is
plain HTTP before HTTPS is enforced (an HSTS response header alone only
protects repeat visits, once the browser has already seen it once).
Preloading (submission to https://hstspreload.org) removes even that
first-request window, entirely browser-side, with none of DNSSEC's
activation risk. Check whether `Strict-Transport-Security` is currently
served with `preload` and whether pyvar.com is already in Chrome's
preload list before doing anything DNSSEC-related — if not done yet, it's
a same-day, zero-outage-risk improvement worth doing on its own merits
regardless of the DNSSEC decision.

---

## Step 0 — Re-verify current state (fresh, every run — do not trust the
## cached values below without re-checking)

Confirmed live as of 2026-08-01 (no `dig`/`whois`/`nslookup` binaries
available in the agent's sandboxed environment — use DNS-over-HTTPS
instead):

```bash
# Nameservers — confirms Aruba hosts the zone
curl -s "https://dns.google/resolve?name=pyvar.com&type=NS"
# → dns.technorail.com, dns2.technorail.com, dns3.arubadns.net,
#   dns4.arubadns.cz — Aruba's own infrastructure, split across TWO
#   distinct backend domains. This matters — see risk profile below.

# DS record at the .com registry — an empty Answer means DNSSEC is OFF
curl -s "https://dns.google/resolve?name=pyvar.com&type=DS"
# → No Answer section, only an Authority/SOA response as of this writing.

# DNSKEY — empty means the zone itself isn't signed either
curl -s "https://dns.google/resolve?name=pyvar.com&type=DNSKEY"

# Registrar of record + registry-side DNSSEC flag, via RDAP
curl -s "https://rdap.verisign.com/com/v1/domain/pyvar.com" | python3 -c "
import json,sys
d = json.load(sys.stdin)
print('secureDNS:', d.get('secureDNS'))
print('nameservers:', [ns.get('ldhName') for ns in d.get('nameservers', [])])
for e in d.get('entities', []):
    if 'registrar' in e.get('roles', []):
        print('registrar:', e['vcardArray'][1][1][3])
"
# Expected today: secureDNS: {'delegationSigned': False}
#                 registrar: Tucows Domains Inc. (IANA registrar ID 69)
```

**Registrar finding — not obvious from Aruba's own panel, and load-
bearing for Step 3 below:** pyvar.com's ICANN-accredited registrar of
record is **Tucows Domains Inc.**, not Aruba. Aruba hosts the DNS zone
(their own nameservers) and — per this RDAP finding — almost certainly
resells domain registration through Tucows/OpenSRS (a very large
white-label wholesale registrar platform used by 9,000+ resellers) behind
their own branded panel. This matters because DNSSEC activation is
technically TWO separate operations — signing the zone (Aruba's job,
since they hold the nameservers) and publishing a DS record at the `.com`
registry (the registrar's job, i.e. Tucows) — even though Aruba's
customer-facing panel presents it as one click ("Attiva DNSSEC" →
"Continua", per their own support docs at guide.aruba.it). Whether
Aruba's backend actually performs both operations atomically and in the
correct order is not confirmable from public documentation — it can only
be observed via Step 5–7's independent checks.

If Step 0's results differ materially from the above (a DS record already
exists, the registrar has changed, or the nameservers differ), STOP and
report the discrepancy before proceeding — the rest of this document
assumes the starting state confirmed above.

---

## Preconditions — confirm ALL before starting

- [ ] At least 2 hours available to actively watch immediately after
      activation — not right before the operator needs to be unreachable.
- [ ] No other DNS record change is in flight, or was made in roughly the
      last 24 hours (Step 0 finds no such change as of this writing —
      re-confirm at run time).
- [ ] dnsviz.net (or equivalent) open and ready to check the moment
      activation happens: https://dnsviz.net/d/pyvar.com/dnssec/
- [ ] The Step 0 DoH commands ready to re-run immediately post-activation
      to independently confirm DS record visibility at the registry — do
      NOT rely on Aruba's own "activated ✅" status message as proof of
      validity.
- [ ] Operator has live access to Aruba's account panel (the agent cannot
      log into or click through Aruba's UI itself).

If any box is unchecked, stop here and reschedule. This is not a change
to make opportunistically.

---

## Sequence

**High-risk task — confirm with the operator before EVERY step below,
not just once at the start.**

1. Operator logs into Aruba's account panel → domain management → DNS
   management panel for pyvar.com.
2. Operator clicks **"Attiva DNSSEC"**.
3. **Aruba shows a confirmation message before the action is final** (per
   their own documentation: "...leggi il messaggio con attenzione...").
   **Operator: read it in full and report back exactly what it says
   before clicking "Continua" — do not click through without reporting
   it first.** This step exists specifically because public Aruba
   documentation does not disclose whether their backend submits the DS
   record to the registry automatically, or requires a separate manual
   step at the registrar (Tucows) level — see the registrar finding in
   Step 0. If this confirmation screen discloses anything about DS
   submission timing, a separate manual step, or anything else not
   already covered by this document, STOP. That is new information
   requiring a fresh decision, not something to continue past on the
   assumption this document already covers it.
4. Once confirmed clear to proceed, operator clicks "Continua".
5. Agent: immediately begin monitoring —
   - Re-run the Step 0 DS/DNSKEY DoH queries every few minutes, watching
     for the DS record to appear at the registry.
   - Once DNSKEY records appear, check dnsviz.net for the zone — confirm
     no ERROR/WARNING chain-of-trust states.
   - Once DS appears at the registry, re-check dnsviz.net — confirm the
     full chain (registry DS → zone DNSKEY → RRSIG) validates cleanly
     with no bogus state.
6. Independently verify resolution AND DNSSEC validation from AT LEAST
   TWO external validating resolvers — not just the agent's default
   resolver:
   ```bash
   # Cloudflare (validates by default)
   curl -s "https://cloudflare-dns.com/dns-query?name=www.pyvar.com&type=A" -H "accept: application/dns-json"
   curl -s "https://cloudflare-dns.com/dns-query?name=pyvar.com&type=A&do=true" -H "accept: application/dns-json"
   # Google (validates by default)
   curl -s "https://dns.google/resolve?name=www.pyvar.com&type=A"
   curl -s "https://dns.google/resolve?name=pyvar.com&type=A&do=true"
   ```
   Confirm `"Status": 0` (NOERROR) on both. With `do=true` (the DNSSEC OK
   bit) set, once the chain is fully live confirm the `AD` (Authenticated
   Data) flag reads `true`. `AD: false` immediately after activation is
   expected during propagation; `Status` other than `0` — especially
   `SERVFAIL` (status 2) — at ANY point during the watch window is the
   failure signal to act on.
7. Confirm the actual application still works end to end through this
   path: `pyvar.com` apex redirect → `www.pyvar.com` → API (`/health`,
   `/docs`) — same checks as docs/p8-task7-dns-ssl-verification.md,
   re-run now against the post-activation state.
8. Keep watching for the full precondition window (2+ hours), not just
   until the first clean check. DNSSEC issues can surface on a delay, as
   different resolvers' caches expire and re-query the newly-signed zone.

---

## Risk profile (read before Step 2)

**This has a larger blast radius than the P8 Task 7 apex redirect
issue.** That bug misrouted traffic (`pyvar.com` → `example.com`) — bad,
but the domain never became unreachable, and it was fixable and
verifiable within the same session. A botched DNSSEC activation is
categorically worse:

- If the DS record published at the registry doesn't correctly match
  what the zone actually serves — wrong hash, wrong algorithm, or the DS
  published before the zone is fully and correctly signed — every
  DNSSEC-**validating** resolver returns `SERVFAIL` for the ENTIRE
  domain: apex, `www`, API, everything. Non-validating resolvers see
  nothing wrong at all, which makes this failure mode easy to miss if
  you only check from one machine/network.
- This isn't a narrow edge case: per APNIC measurement data, roughly
  **38% of global DNS queries** go through validating resolvers (Google
  8.8.8.8, Cloudflare 1.1.1.1, and Quad9 9.9.9.9 all validate by default,
  plus many ISP/corporate resolvers) — that is the realistic size of the
  affected audience if this goes wrong, not a hypothetical edge case.
- The five documented causes of post-activation SERVFAIL: (1) DS record
  missing or not yet propagated, (2) DS hash doesn't match the published
  DNSKEY, (3) expired RRSIG signatures (not a first-activation risk, but
  relevant to future key rotation), (4) DS/DNSKEY algorithm mismatch,
  (5) stale resolver caching. Causes (1), (2), and (4) are exactly what
  would happen if Aruba's "sign zone → submit DS" backend ordering isn't
  correct — which cannot be confirmed from outside, only observed via
  Steps 5–7.
- **Aruba-specific risk, grounded in this project's own history, not
  generic DNSSEC theory:** pyvar.com's zone is served across FOUR
  nameservers split between TWO backend domains (`technorail.com` and
  `arubadns.net`/`.cz`). P8 Task 7 already demonstrated that Aruba's
  infrastructure can have one component silently stale (their forwarding
  proxy) while another looked fine — the same pattern could recur here,
  with DNSSEC signing rolling out unevenly across those four
  nameservers, causing intermittent (not uniform) SERVFAIL depending on
  which nameserver a given query happens to land on.
- **The propagation/exposure window is long, not short.** DS records at
  the TLD level are typically cached with a 24–48 hour TTL. This cuts
  both ways: a bad activation doesn't just fail during a brief window
  and then quietly recover — resolvers that already cached the bad state
  keep failing for up to that TTL even after the root cause is fixed.
  Budget accordingly; this is not a "watch for ten minutes and move on"
  change.

---

## Rollback

If Steps 6–7 show `SERVFAIL`, `AD: false` persisting well past a normal
propagation delay, or any other sign of a broken chain of trust:

1. Operator: Aruba panel → "Disattiva DNSSEC" → confirm.
2. This is the correct fix, but **not instant** — resolvers that already
   cached the bad DS/DNSKEY state keep failing until that cached state's
   TTL expires, which per the 24–48 hour DS TTL above could mean a
   meaningful share of the world sees the domain as broken for up to two
   days after the revert.
3. Because of that, **this is not a change to make unless a genuinely
   guaranteed-quiet next 24 hours can be spared** — both for the initial
   activation watch, and for the possibility of needing to roll back and
   then wait out the recovery window on top of that.

---

## Exit gate

- [ ] DS record confirmed visible at the `.com` registry via an
      independent DoH check (Step 0's query re-run, or equivalent) — NOT
      just Aruba's own panel status.
- [ ] dnsviz.net (or equivalent) shows a fully valid chain of trust, no
      bogus/error states, for pyvar.com.
- [ ] `pyvar.com`, `www.pyvar.com`, and the API endpoints (`/health`,
      `/docs`) confirmed still resolving AND functionally correct, from
      AT LEAST TWO external DNSSEC-validating resolvers (e.g. Cloudflare
      1.1.1.1 / Google 8.8.8.8 via DoH — Step 6).
- [ ] Monitored continuously for the full precondition watch window
      (2+ hours), with no SERVFAIL/bogus state observed at any point —
      not just the first check immediately after activation.
- [ ] Aruba's "Continua" confirmation screen text was read and reported
      before proceeding (Step 3). If it disclosed a separate manual
      DS-submission step, that step is confirmed complete too before
      this exit gate is considered met.

Do not declare this done on the strength of Aruba's own status indicator
alone — every box above requires independent, external verification.

---

## Update (2026-08-27) — bundled with HSTS preload; likely combined fix is a DNS-hosting migration, not an Aruba setting

Deferred again, alongside a related item: getting `pyvar.com` onto the
HSTS preload list. Both now share the same root blocker and are being
tracked together rather than as two separate Aruba-panel actions.

### How HSTS preload connects to this doc

A CloudFront `ResponseHeadersPolicy` (PR #280) added a correct
`Strict-Transport-Security` header (`max-age=31536000; includeSubDomains;
preload`) to `www.pyvar.com`, fully controlled by CloudFront. This does
**not** get the domain preload-eligible on its own: hstspreload.org's
`/api/v2/preloadable` endpoint rejects `www.pyvar.com` outright —
`domain.is_subdomain`, *"we only accept automated preload list
submissions of whole registered domains"* — confirmed via a live API
call, not assumed. `includeSubDomains` on the apex is what's supposed to
extend coverage to `www` automatically; there is no path to preload a
bare subdomain while excluding the apex.

The apex itself (`pyvar.com`) is the only valid submission target, and it
currently has no HSTS header at all — confirmed live (`server:
aruba-proxy`, no `strict-transport-security` on either
`http://pyvar.com/` or `https://pyvar.com/`, both just 301 to
`www.pyvar.com`). Per `docs/domain-cutover-stage-b-c-plan.md`, this proxy
is Aruba's own domain-forwarding service, entirely outside CloudFront/CDK
control — the exact same black box this DNSSEC doc already treats as
unreachable via API/CLI.

### Why this probably isn't a small Aruba-panel fix (unverified, needs confirming)

Per input relayed from the user (originating from another AI assistant's
answer — **not independently verified**, treat the specifics below as
leads to confirm, not settled fact): if the domain only has Aruba's
"Gestione DNS con Redirect" (DNS Management with Redirect) service and no
actual hosting plan, there is no server config surface to inject a custom
HSTS header onto the forwarding response — that service reportedly maps
DNS/does a basic server-side forward only, nothing more.

If accurate, the two commonly-suggested workarounds are both bigger than
a settings toggle:
- **Migrate `pyvar.com`'s authoritative nameservers to Cloudflare**
  (free tier includes a one-click HSTS toggle and redirect rules). This
  is not a small change — it moves the *entire* DNS zone off Aruba, not
  just the apex forwarding rule. Every record currently at Aruba (MX for
  email, the `www` CNAME, everything) would need replicating and cutting
  over. Same risk *class* as the Stage B/C domain cutover already done
  (`docs/domain-cutover-stage-b-c-plan.md`), likely larger blast radius.
  Worth noting as a genuine upside if this path is ever taken: Cloudflare
  has its own well-regarded, single-provider, effectively one-click
  DNSSEC support — meaningfully simpler than Aruba's ambiguous two-party
  (Aruba-signs, Tucows-publishes-DS) flow this doc spends most of its
  length on. A Cloudflare migration would plausibly solve **both** this
  doc's DNSSEC item and the HSTS-apex item in the same move.
- **Point the apex at a third-party redirect-as-a-service tool**
  (e.g. Redirect.pizza) that handles TLS + header injection. Smaller
  footprint than a full DNS migration, but introduces an unvetted
  third-party vendor into the trust chain for a regulatory-grade
  platform's public domain — real vetting (reliability, security
  posture, who's actually terminating TLS for `pyvar.com`) needed before
  this is anywhere near production, not before.

### Status

Not investigated further, not actioned. Bundled with DNSSEC for the
evolutive/maintenance phase — post-launch, not before. If picked up, the
first step is confirming the Aruba capability claim above directly
(their panel or support), then evaluating a Cloudflare DNS migration as
the likely combined fix for both items, with its own dedicated
investigation and runbook (mirroring this doc's and
`docs/domain-cutover-stage-b-c-plan.md`'s level of rigor) before any live
change — not a decision to make inline against a live zone.
