#!/usr/bin/env bash
# scripts/validate_pyvar_local_release.sh: validate a PUBLISHED pyvar Local release in real Docker.
#
# Reasoning:
# - The release pipeline (pyvar-cdk/stacks/local_package_stack.py) builds and tests the image in Docker BEFORE it is
#   saved and uploaded; nothing checks what a user actually gets: the downloaded file, `docker load`, `docker run`.
#   This does, on the real asset: it downloads it, compares size and sha256 with the GitHub release's own digest,
#   loads it, checks the image config, runs the default command, the engine tests the release is gated on, a seeded
#   VaR call twice (a fixed seed must give byte-identical output), and the same call as a non-root user and with a
#   read-only filesystem.
# - Run by .github/workflows/pyvar-local-release-validate.yml (a standard amd64 Linux runner), or by hand on any
#   machine with Docker:  bash scripts/validate_pyvar_local_release.sh [pyvar-local-v0-<8 hex>]   (no tag: the newest
#   release whose tag starts pyvar-local-v0-). On a non-amd64 machine it adds --platform linux/amd64 (emulation).
# - Values every release must satisfy are checked for every tag (load works, config, exit codes, the engine tests
#   pass, the output is identical twice, the four result keys exist). Values that belong to one build (function count,
#   test count, the four numbers) are checked only for the tag they were recorded for (see EXPECT below); for a new
#   release they are printed, and you add them when you have read them.
# - The image runs as root and bakes Numba's cache into /app. Run as another user, or on a read-only filesystem, a
#   Numba-compiled function fails ("cannot cache function ... no locator available"), even `list` and the tests.
#   Found by the first real run (2026-11-20). So the bare non-root and read-only runs are WARNINGS (a known limit,
#   documented in pyvar-local/README.md), while the runs WITH the documented workaround (a writable cache directory:
#   `-e HOME=/tmp`, or `--tmpfs /tmp -e NUMBA_CACHE_DIR=/tmp/numba`) must give the same numbers or the check FAILS.
# - Nothing is pushed, no secret is read. Only GITHUB_TOKEN/GH_TOKEN, if set, is sent, and only to api.github.com
#   (to avoid its anonymous rate limit); the download itself is anonymous. A GitHub step summary is written when
#   $GITHUB_STEP_SUMMARY is set. $PYVAR_LOCAL_ARCHIVE (a path) skips the download, for tests.
#
# Exit codes: 0 every check passed (warnings allowed); 1 at least one check failed; 2 bad arguments or a missing tool.

set -uo pipefail

REPO="${GITHUB_REPOSITORY:-fibtecltd/pyvar}"
TAG="${1:-}"
PREFIX="pyvar-local-v0-"
TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}"
FAILS=0
WARNS=0
SUMMARY=()

say() { printf '%s\n' "$*"; }
record() { SUMMARY+=("| $1 | $2 | $3 |"); say "$1  $2: $3"; }
pass() { record "PASS" "$1" "${2:-}"; }
fail() { record "FAIL" "$1" "${2:-}"; FAILS=$((FAILS + 1)); }
warn() { record "WARN" "$1" "${2:-}"; WARNS=$((WARNS + 1)); }
note() { record "NOTE" "$1" "${2:-}"; }
eq() { if [ "$2" = "$3" ]; then pass "$1" "${4:-$2}"; else fail "$1" "got '$2', expected '$3'"; fi; } # eq label got want [detail]

for tool in docker curl python3; do
  command -v "$tool" >/dev/null 2>&1 || { say "missing tool: $tool"; exit 2; }
done

sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
now_ms() { python3 -c 'import time; print(int(time.time() * 1000))'; }

api() { # api <path>: GET from the GitHub API, with the token if there is one
  local headers=(-H "Accept: application/vnd.github+json")
  [ -n "$TOKEN" ] && headers+=(-H "Authorization: Bearer $TOKEN")
  curl -fsS --retry 3 "${headers[@]}" "https://api.github.com/repos/$REPO/$1"
}

# ── which release ──────────────────────────────────────────────────────────────────────────────────────────────
if [ -z "$TAG" ] || [ "$TAG" = "latest" ]; then
  TAG="$(api "releases?per_page=50" | PREFIX="$PREFIX" python3 -c '
import json, os, sys
for release in json.load(sys.stdin):
    if release["tag_name"].startswith(os.environ["PREFIX"]) and not release.get("draft"):
        print(release["tag_name"]); break
')" || { say "could not read the releases"; exit 2; }
  [ -n "$TAG" ] || { say "no release with a tag starting $PREFIX"; exit 2; }
fi
if ! [[ "$TAG" =~ ^pyvar-local-v0-[0-9a-f]{8}$ ]]; then
  say "not a pyvar Local release tag: $TAG"
  exit 2
fi
say "Validating $REPO release $TAG"

# What was recorded for the one release that has been read so far.
EXPECT_FUNCTIONS=""; EXPECT_TESTS=""; EXPECT_VAR_PCT=""; EXPECT_VAR_ABS=""; EXPECT_CVAR_PCT=""; EXPECT_CVAR_ABS=""
EXPECT_SIZE=""
case "$TAG" in
  pyvar-local-v0-3dbc102a)
    EXPECT_FUNCTIONS=387; EXPECT_TESTS=19; EXPECT_SIZE=570477502
    EXPECT_VAR_PCT=0.033103; EXPECT_VAR_ABS=33103.32; EXPECT_CVAR_PCT=0.036512; EXPECT_CVAR_ABS=36512.38
    ;;
esac

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"; [ -n "${IMAGE:-}" ] && docker rmi "$IMAGE" >/dev/null 2>&1' EXIT
cd "$WORK" || exit 2

# ── 1. the machine ─────────────────────────────────────────────────────────────────────────────────────────────
ARCH="$(uname -m)"
PLATFORM=()
if [ "$ARCH" != "x86_64" ] && [ "$ARCH" != "amd64" ]; then
  PLATFORM=(--platform linux/amd64)
  note "machine" "$ARCH is not amd64: every run uses --platform linux/amd64 (emulation, slower)"
fi
SERVER="$(docker version --format '{{.Server.Version}} {{.Server.Os}}/{{.Server.Arch}}' 2>/dev/null || true)"
if [ -z "$SERVER" ]; then fail "docker" "no Docker daemon answered"; exit 1; fi
note "docker" "server $SERVER, machine $ARCH"

# ── 2. the file ────────────────────────────────────────────────────────────────────────────────────────────────
URL="https://github.com/$REPO/releases/download/$TAG/pyvar-local.tar.gz"
if [ -n "${PYVAR_LOCAL_ARCHIVE:-}" ]; then
  cp "$PYVAR_LOCAL_ARCHIVE" pyvar-local.tar.gz
else
  curl -fsSL --retry 3 --retry-delay 5 -o pyvar-local.tar.gz "$URL" || { fail "download" "$URL"; exit 1; }
fi
SIZE="$(stat -c %s pyvar-local.tar.gz 2>/dev/null || stat -f %z pyvar-local.tar.gz)"
SHA="$(sha256 pyvar-local.tar.gz)"
note "archive" "$SIZE bytes, sha256 $SHA"
if [ -n "$EXPECT_SIZE" ]; then eq "size" "$SIZE" "$EXPECT_SIZE"; fi
ASSET="$(api "releases/tags/$TAG" 2>/dev/null | python3 -c '
import json, sys
for asset in json.load(sys.stdin).get("assets", []):
    if asset["name"] == "pyvar-local.tar.gz":
        print(asset["size"], (asset.get("digest") or "").replace("sha256:", "")); break
' 2>/dev/null)" || ASSET=""
if [ -z "$ASSET" ]; then
  warn "release API" "could not read the asset's size and digest"
else
  API_SIZE="${ASSET%% *}"; API_DIGEST="${ASSET#* }"
  eq "size vs release API" "$SIZE" "$API_SIZE"
  if [ -z "$API_DIGEST" ] || [ "$API_DIGEST" = "$ASSET" ]; then
    note "digest" "the release API gave none"
  else
    eq "sha256 vs release API" "$SHA" "$API_DIGEST"
  fi
fi

# ── 3. docker load and the image config ────────────────────────────────────────────────────────────────────────
LOADED="$(docker load -i pyvar-local.tar.gz 2>&1)"; STATUS=$?
IMAGE="$(printf '%s\n' "$LOADED" | sed -n 's/^Loaded image: //p' | head -1)"
if [ "$STATUS" -ne 0 ] || [ -z "$IMAGE" ]; then
  fail "docker load" "exit $STATUS: $(printf '%s' "$LOADED" | tail -2 | tr '\n' ' ')"
  exit 1
fi
pass "docker load" "$IMAGE"
CONFIG="$(docker image inspect "$IMAGE" --format '{{json .Config.Entrypoint}}|{{json .Config.Cmd}}|{{.Config.WorkingDir}}|{{.Config.User}}|{{.Architecture}}|{{.Os}}|{{.Created}}|{{len .RootFS.Layers}}')"
IFS='|' read -r C_ENTRY C_CMD C_DIR C_USER C_ARCH C_OS C_CREATED C_LAYERS <<<"$CONFIG"
eq "entrypoint" "$C_ENTRY" '["python","-m","pyvar_local.cli"]'
eq "default command" "$C_CMD" '["list"]'
eq "working directory" "$C_DIR" "/app"
eq "platform" "$C_ARCH/$C_OS" "amd64/linux"
note "image" "created $C_CREATED, $C_LAYERS layers, user '${C_USER:-root}'"
note "environment" "$(docker image inspect "$IMAGE" --format '{{json .Config.Env}}')"

# ── 4. the default command ─────────────────────────────────────────────────────────────────────────────────────
docker run --rm ${PLATFORM[@]+"${PLATFORM[@]}"} "$IMAGE" >list.out 2>list.err; STATUS=$?
LINES="$(wc -l <list.out | tr -d ' ')"
HITS="$(grep -c 'montecarlo.run_monte_carlo_var' list.out || true)"
if [ "$STATUS" -eq 0 ]; then
  pass "default command runs" "exit 0, $LINES functions"
else
  fail "default command runs" "exit $STATUS: $(tail -3 list.err | tr '\n' ' ')"
fi
eq "known function listed once" "$HITS" "1" "montecarlo.run_monte_carlo_var"
if [ -n "$EXPECT_FUNCTIONS" ]; then eq "function count" "$LINES" "$EXPECT_FUNCTIONS"; fi

# ── 5. the tests the release is gated on ───────────────────────────────────────────────────────────────────────
docker run --rm ${PLATFORM[@]+"${PLATFORM[@]}"} --entrypoint pytest "$IMAGE" /app/tests/test_engine.py -q -p no:cacheprovider >pytest.out 2>&1; STATUS=$?
PASSED="$(grep -Eo '[0-9]+ passed' pytest.out | tail -1 | cut -d' ' -f1)"
if [ "$STATUS" -eq 0 ] && [ -n "$PASSED" ]; then
  pass "engine tests" "$PASSED passed"
else
  fail "engine tests" "exit $STATUS: $(tail -5 pytest.out | tr '\n' ' ')"
fi
if [ -n "$EXPECT_TESTS" ] && [ -n "$PASSED" ]; then
  eq "test count" "$PASSED" "$EXPECT_TESTS"
fi

# ── 6. a seeded call, twice ────────────────────────────────────────────────────────────────────────────────────
python3 -c 'import json,random;random.seed(0);print(json.dumps({"returns":[round(random.gauss(0.0005,0.012),6) for _ in range(30)],"portfolio_value":1000000,"confidence_level":0.99,"horizon_days":1,"n_simulations":1000,"seed":1}))' >params.json
call() { # call <out> <err> [docker options...]: the seeded VaR call
  local out="$1" err="$2"; shift 2
  docker run --rm ${PLATFORM[@]+"${PLATFORM[@]}"} "$@" "$IMAGE" call montecarlo run_monte_carlo_var --params "$(cat params.json)" >"$out" 2>"$err"
}
numbers() { # numbers <file>: var_pct var_abs cvar_pct cvar_abs, or nothing if it is not the expected JSON
  python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(*[d[k] for k in ("var_pct", "var_abs", "cvar_pct", "cvar_abs")])
except Exception:
    pass
' "$1"
}
START=$(now_ms); call run1.json run1.err; S1=$?; T1=$(( $(now_ms) - START ))
START=$(now_ms); call run2.json run2.err; S2=$?; T2=$(( $(now_ms) - START ))
N1="$(numbers run1.json)"
if [ "$S1" -eq 0 ] && [ "$S2" -eq 0 ] && [ -n "$N1" ]; then
  pass "seeded call" "var_pct var_abs cvar_pct cvar_abs = $N1 (first $T1 ms, second $T2 ms)"
else
  fail "seeded call" "exits $S1 and $S2: $(tail -3 run1.err | tr '\n' ' ')"
fi
if cmp -s run1.json run2.json; then pass "deterministic" "two runs byte-identical"; else fail "deterministic" "two runs differ"; fi
if [ -n "$EXPECT_VAR_PCT" ]; then
  eq "recorded numbers" "$N1" "$EXPECT_VAR_PCT $EXPECT_VAR_ABS $EXPECT_CVAR_PCT $EXPECT_CVAR_ABS"
fi

# ── 7. what the chroot test could not show ─────────────────────────────────────────────────────────────────────
variant() { # variant <WARN|FAIL: what a failure counts as> <label> [docker options...]
  local on_fail="$1" label="$2"; shift 2
  call "v.json" "v.err" "$@"; local status=$?
  if [ "$status" -eq 0 ] && [ "$(numbers v.json)" = "$N1" ]; then
    pass "$label" "same numbers"
  else
    case "$on_fail" in
      WARN) warn "$label" "exit $status: $(tail -1 v.err | cut -c1-160)" ;;
      *) fail "$label" "exit $status: $(tail -1 v.err | cut -c1-160)" ;;
    esac
  fi
}
# known limits (warnings): no writable cache directory
variant WARN "as a non-root user, no workaround (--user 1000:1000)" --user 1000:1000
variant WARN "read-only filesystem, no workaround (--read-only)" --read-only
# the documented workarounds (failures): pyvar-local/README.md
variant FAIL "non-root with HOME=/tmp" --user 1000:1000 -e HOME=/tmp
variant FAIL "non-root with a writable cache (tmpfs /tmp, NUMBA_CACHE_DIR)" --user 1000:1000 --tmpfs /tmp -e NUMBA_CACHE_DIR=/tmp/numba
variant FAIL "read-only with a writable cache (tmpfs /tmp, NUMBA_CACHE_DIR)" --read-only --tmpfs /tmp -e NUMBA_CACHE_DIR=/tmp/numba
variant FAIL "read-only and non-root with a writable cache" --read-only --user 1000:1000 --tmpfs /tmp -e NUMBA_CACHE_DIR=/tmp/numba

# ── result ─────────────────────────────────────────────────────────────────────────────────────────────────────
say ""
say "$TAG: $FAILS failed, $WARNS warning(s)"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "## pyvar Local release \`$TAG\` in Docker"
    echo ""
    echo "| Result | Check | Detail |"
    echo "| --- | --- | --- |"
    printf '%s\n' "${SUMMARY[@]}"
    echo ""
    echo "**$FAILS failed, $WARNS warning(s).**"
  } >>"$GITHUB_STEP_SUMMARY"
fi
[ "$FAILS" -eq 0 ]
