#!/bin/bash
# pyvar-phase.sh — master switcher UNIFIED v3
SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ $# -eq 0 ] || [[ "$1" == "list" ]] && { echo "Phases: p1 p2 p3 p4 p5 p6 p7 p8 p9"; echo "Usage: ./pyvar-phase.sh <id> [--dry-run|--status|--at-only]"; exit 0; }
S="$SD/phase-$1.sh"; shift; [ -f "$S" ] || { echo "Unknown phase. Run: ./pyvar-phase.sh list"; exit 1; }
exec "$S" "$@"
