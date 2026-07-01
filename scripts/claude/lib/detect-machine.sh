#!/bin/sh
# lib/detect-machine.sh
# Detects host machine and exports resource allocation variables.
# Source this file; do not execute it directly.
#
# Exports:
#   MACHINE          intel | m4
#   CLAUDE_CPUS      CPU limit for claude container
#   CLAUDE_MEM       Memory limit for claude container
#   WORKER_CPUS      CPU limit for Celery worker
#   WORKER_MEM       Memory limit for Celery worker
#   API_CPUS         CPU limit for pyvar-api
#   API_MEM          Memory limit for pyvar-api
#   AGENT_TEAMS_OK   1 if Agent Teams is viable, 0 if not
#   MAX_TEAMMATES    Max parallel teammates (0 on Intel)
#   DOCKER_PLATFORM  --platform flag value for M4 cross-builds

# Allow manual override via environment
if [ -n "${PYVAR_MACHINE:-}" ]; then
    MACHINE="$PYVAR_MACHINE"
else
    ARCH=$(uname -m)
    case "$ARCH" in
        arm64)  MACHINE="m4"    ;;
        x86_64) MACHINE="intel" ;;
        *)      MACHINE="intel" ;;  # safe default
    esac
fi

case "$MACHINE" in

    m4)
        # Apple M4 4.4 GHz · 16 GB unified memory
        # Docker Desktop on Apple Silicon is native ARM64 — very efficient.
        # 10 cores total (4 performance + 6 efficiency).
        # macOS + Docker Desktop overhead: ~4-5 GB, ~2 cores.
        # Available for containers: ~11 GB, ~8 cores.
        #
        # Claude container gets 4 CPUs / 5 GB:
        #   Agent Teams lead spawns up to 4 sub-agents, each sharing
        #   this allocation. 4 CPUs / 4 agents = 1 core per agent.
        #   Memory: ~1.2 GB per agent for Opus 4.8 context + claude binary.
        #
        # Worker gets 4 CPUs / 4 GB:
        #   Monte Carlo at 100k paths with prange uses all available cores.
        #   4 CPUs saturates the physical performance cores without starving
        #   the host completely.
        CLAUDE_CPUS="4.0"
        CLAUDE_MEM="5g"
        WORKER_CPUS="4.0"
        WORKER_MEM="4g"
        API_CPUS="2.0"
        API_MEM="2g"
        AGENT_TEAMS_OK=1
        MAX_TEAMMATES=4
        DOCKER_PLATFORM="linux/arm64"
        ;;

    intel)
        # Intel Core i5 2.5 GHz Dual-Core · 16 GB
        # 2 physical cores, 4 logical (hyperthreading).
        # Docker Desktop on macOS x86: ~1 GB overhead per active container.
        # macOS baseline: ~4 GB.
        # Available: ~10 GB, ~3 usable cores.
        #
        # AGENT TEAMS NOT VIABLE:
        #   Opus 4.8 × 4 parallel instances on 4 logical cores =
        #   severe thrashing. Each agent response takes 3-5× longer.
        #   Sequential is faster in practice on this hardware.
        #
        # Claude container: 1.0 CPU / 2 GB
        #   Leaves room for worker and the host UI.
        # Worker: 1.5 CPU / 4 GB
        #   Monte Carlo dominates runtime — give it the most CPU.
        #   4 GB handles 100k-path simulation + numpy arrays.
        CLAUDE_CPUS="1.0"
        CLAUDE_MEM="2g"
        WORKER_CPUS="1.5"
        WORKER_MEM="4g"
        API_CPUS="0.5"
        API_MEM="1g"
        AGENT_TEAMS_OK=0
        MAX_TEAMMATES=0
        DOCKER_PLATFORM="linux/amd64"
        ;;

    *)
        echo "[detect-machine] WARNING: unknown machine '$MACHINE', using Intel safe defaults."
        MACHINE="intel"
        CLAUDE_CPUS="1.0"
        CLAUDE_MEM="2g"
        WORKER_CPUS="1.5"
        WORKER_MEM="4g"
        API_CPUS="0.5"
        API_MEM="1g"
        AGENT_TEAMS_OK=0
        MAX_TEAMMATES=0
        DOCKER_PLATFORM="linux/amd64"
        ;;
esac

export MACHINE CLAUDE_CPUS CLAUDE_MEM WORKER_CPUS WORKER_MEM \
       API_CPUS API_MEM AGENT_TEAMS_OK MAX_TEAMMATES DOCKER_PLATFORM
