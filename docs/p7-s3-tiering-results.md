# P7 Task 5 — S3 Intelligent-Tiering verification

## Checks

**1. Is Intelligent-Tiering enabled on `pyvar-dev-results-{account}`?**
Yes — confirmed both in code (`data_stack.py`'s `intelligent_tiering_configurations`)
and live via `aws s3api get-bucket-intelligent-tiering-configuration`:

```json
{
  "Id": "AllObjects",
  "Status": "Enabled",
  "Tierings": [
    {"Days": 90, "AccessTier": "ARCHIVE_ACCESS"},
    {"Days": 180, "AccessTier": "DEEP_ARCHIVE_ACCESS"}
  ]
}
```

Matches the CDK code exactly.

**2. Do objects transition to IA after 30 days?**
The 30-day Frequent→Infrequent Access move is a fixed, automatic property of
the `INTELLIGENT_TIERING` storage class itself — AWS doesn't expose it as a
configurable parameter (only the *optional* Archive/Deep-Archive sub-tiers,
seen above, are configurable). So there's nothing to misconfigure there.

**However, a real, separate misconfiguration was found and fixed**: nothing
in the stack ever actually moved objects *into* the `INTELLIGENT_TIERING`
storage class in the first place. `intelligent_tiering_configurations` only
governs the archive/deep-archive sub-tiers for objects *already* in that
storage class — it does not cause `STANDARD`-class objects to migrate there.
That requires either `StorageClass=INTELLIGENT_TIERING` at upload time, or a
lifecycle `Transition`. Neither existed:

- `storage/s3.py`'s `write_result_to_s3()` calls `put_object(...)` with no
  `StorageClass` argument — defaults to `STANDARD`.
- `data_stack.py`'s `lifecycle_rules` had `ExpireOldResults` (hard delete
  after `result_retention_days`) and `CleanupIncompleteUploads` only — no
  `Transition` to `INTELLIGENT_TIERING`.

So as configured, the entire archive/deep-archive tiering setup was
**inert** — any object written would sit on `STANDARD` storage for its
whole life (until the 90-day hard-delete rule removed it), contradicting the
stack's own docstring ("S3 Intelligent-Tiering automatically moves old
Parquet simulation results to cheaper tiers").

**Fix applied**: added a `TransitionToIntelligentTiering` lifecycle rule
(`transition_after=Duration.days(0)`) so every object moves into
`INTELLIGENT_TIERING` immediately, at which point AWS's automatic 30-day
IA move and the existing 90/180-day archive sub-tiers apply as originally
intended. Verified via `aws_cdk.assertions.Template` against the
synthesized `DataStack` in isolation — the bucket's `LifecycleConfiguration`
now has 3 rules, with the new one showing
`Transitions: [{StorageClass: INTELLIGENT_TIERING, TransitionInDays: 0}]`.
Also ran `cdk synth` for the full app — no errors. No `cdk deploy` was run.

**3. Are there objects old enough to have transitioned?**
No — stronger than "too new": `aws s3api list-objects-v2` on the live bucket
returns **zero objects** (`KeyCount: 0`). Digging into why: `storage/s3.py`'s
`write_result_to_s3()` has **zero callers anywhere in the codebase** —
`tasks/var_task.py` never invokes it; results currently only reach the
Celery/Redis result backend, never S3. This is a separate, more fundamental
gap than a tiering misconfiguration (S3 result storage isn't wired into the
job pipeline at all yet) and is **out of scope for this task** — flagging it
rather than fixing it, since wiring up S3 result persistence is a feature
change well beyond "verify Intelligent-Tiering config." Cannot verify actual
transition behaviour (0 objects to observe), but the configuration is now
confirmed correct for whenever objects do land there.

## Summary

| Check | Result |
|---|---|
| Intelligent-Tiering enabled | Yes, confirmed live |
| 30-day IA transition | Automatic AWS behaviour, not configurable — N/A |
| Archive/deep-archive sub-tiers configured | Yes (90d / 180d), confirmed live |
| Objects actually reach `INTELLIGENT_TIERING` | **No — fixed** (missing lifecycle transition) |
| Transition behaviour observed | Cannot verify — bucket has 0 objects (separate gap: S3 write path unwired) |
