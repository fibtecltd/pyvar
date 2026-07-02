#!/bin/bash
# pyvar.com Phase P5b — UNIFIED v3
# Remainder Testing | Basel backtest, FRTB PAT, Load, Security, Residency
# Usage: ./phase-p5b.sh [--dry-run|--status|--at-only]
set -euo pipefail
DRY_RUN=0; STATUS_ONLY=0; AT_ONLY=0
for a in "$@"; do case $a in --dry-run) DRY_RUN=1;; --status) STATUS_ONLY=1;; --at-only) AT_ONLY=1;; esac; done
run() { [ $DRY_RUN -eq 1 ] && echo "[dry-run] $*" || { echo "[exec] $*"; eval "$@"; }; }

toggle_at() {
  local mode="$1" settings="$HOME/.claude/settings.json"
  [ -f "$settings" ] || echo '{}' > "$settings"
  if [ "$mode" = "on" ]; then
    [ $DRY_RUN -eq 0 ] && python3 -c "
import json; f='$settings'
s=json.load(open(f)); s.setdefault('env',{})['CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS']='1'
json.dump(s,open(f,'w'),indent=2)" && echo "  🤝 Agent Teams ON  (restart: claude --dangerously-skip-permissions --model claude-opus-4-8)"
    [ $DRY_RUN -eq 1 ] && echo "[dry-run] Enable Agent Teams"
  else
    [ $DRY_RUN -eq 0 ] && python3 -c "
import json; f='$settings'
s=json.load(open(f)); s.get('env',{}).pop('CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS',None)
json.dump(s,open(f,'w'),indent=2)" && echo "  —  Agent Teams OFF"
    [ $DRY_RUN -eq 1 ] && echo "[dry-run] Disable Agent Teams"
  fi
}
install_if_missing() {
  local p="$1" n="${1%%@*}"
  claude plugins list 2>/dev/null | grep -q "^$n" \
    && echo "  (ok) $n" \
    || { echo "  📦 $p"; [ $DRY_RUN -eq 0 ] && claude plugins install "$p" || echo "[dry-run] install $p"; }
}

[ $STATUS_ONLY -eq 1 ] && { claude plugins list 2>/dev/null || true; exit 0; }

echo "╔══════════════════════════════════════════════════════╗"
echo "║ pyvar · P5b: Remainder Testing                         ║"
echo "║ Basel · FRTB · Load · Security · Residency             ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
# Remainder testing stack: security-scanning, performance-testing-review,
# api-testing-observability, compliance, scientific-computing.
# Agent Teams ON: 3 parallel teammates (backtesting, load+security, residency).
echo ""
[ $AT_ONLY -eq 1 ] && { toggle_at "on"; exit 0; }

# Install new plugins (idempotent)
install_if_missing "agent-orchestration@claude-code-workflows"
install_if_missing "api-testing-observability@claude-code-workflows"
install_if_missing "commit-commands@claude-plugins-official"
install_if_missing "compliance@JoelLewis-finance-skills"
install_if_missing "context7@claude-plugins-official"
install_if_missing "performance-testing-review@claude-code-workflows"
install_if_missing "pr-review-toolkit@claude-plugins-official"
install_if_missing "pytest-assistant@python-backend-plugins"
install_if_missing "scientific-computing@K-Dense-AI-scientific-agent-skills"
install_if_missing "security-scanning@claude-code-workflows"

# ENABLE
echo "  ✅ [workflow ] agent-orchestration"
run claude plugins enable agent-orchestration@claude-code-workflows
echo "  ✅ [workflow ] api-testing-observability"
run claude plugins enable api-testing-observability@claude-code-workflows
echo "  ✅ [official ] commit-commands"
run claude plugins enable commit-commands@claude-plugins-official
echo "  ✅ [joel-fin ] compliance"
run claude plugins enable compliance@JoelLewis-finance-skills
echo "  ✅ [workflow ] comprehensive-review"
run claude plugins enable comprehensive-review@claude-code-workflows
echo "  ✅ [official ] context7"
run claude plugins enable context7@claude-plugins-official
echo "  ✅ [skills   ] finance-skills"
run claude plugins enable finance-skills@claude-code-skills
echo "  ✅ [official ] github"
run claude plugins enable github@claude-plugins-official
echo "  ✅ [workflow ] performance-testing-review"
run claude plugins enable performance-testing-review@claude-code-workflows
echo "  ✅ [official ] pr-review-toolkit"
run claude plugins enable pr-review-toolkit@claude-plugins-official
echo "  ✅ [official ] pyright-lsp"
run claude plugins enable pyright-lsp@claude-plugins-official
echo "  ✅ [py-back  ] pytest-assistant"
run claude plugins enable pytest-assistant@python-backend-plugins
echo "  ✅ [workflow ] quantitative-trading"
run claude plugins enable quantitative-trading@claude-code-workflows
echo "  ✅ [official ] ralph-loop"
run claude plugins enable ralph-loop@claude-plugins-official
echo "  ✅ [sci-agent] scientific-computing"
run claude plugins enable scientific-computing@K-Dense-AI-scientific-agent-skills
echo "  ✅ [workflow ] security-scanning"
run claude plugins enable security-scanning@claude-code-workflows
echo "  ✅ [skills   ] statistical-analyst"
run claude plugins enable statistical-analyst@claude-code-skills
echo "  ✅ [workflow ] cloud-infrastructure"
run claude plugins enable cloud-infrastructure@claude-code-workflows

# DISABLE
echo "  —  [workflow ] api-scaffolding"
run claude plugins disable api-scaffolding@claude-code-workflows
echo "  —  [workflow ] application-performance"
run claude plugins disable application-performance@claude-code-workflows
echo "  —  [workflow ] backend-development"
run claude plugins disable backend-development@claude-code-workflows
echo "  —  [official ] claude-md-management"
run claude plugins disable claude-md-management@claude-plugins-official
echo "  —  [py-back  ] clean-code"
run claude plugins disable clean-code@python-backend-plugins
echo "  —  [workflow ] code-documentation"
run claude plugins disable code-documentation@claude-code-workflows
echo "  —  [workflow ] data-engineering"
run claude plugins disable data-engineering@claude-code-workflows
echo "  —  [workflow ] data-analysis"
run claude plugins disable data-analysis@K-Dense-AI-scientific-agent-skills 2>/dev/null || true
echo "  —  [workflow ] database-cloud-optimization"
run claude plugins disable database-cloud-optimization@claude-code-workflows
echo "  —  [skills   ] docker-development"
run claude plugins disable docker-development@claude-code-skills
echo "  —  [workflow ] documentation-generation"
run claude plugins disable documentation-generation@claude-code-workflows
echo "  —  [official ] feature-dev"
run claude plugins disable feature-dev@claude-plugins-official
echo "  —  [official ] frontend-design"
run claude plugins disable frontend-design@claude-plugins-official
echo "  —  [workflow ] frontend-mobile-development"
run claude plugins disable frontend-mobile-development@claude-code-workflows
echo "  —  [skills   ] karpathy-coder"
run claude plugins disable karpathy-coder@claude-code-skills
echo "  —  [skills   ] terraform-patterns"
run claude plugins disable terraform-patterns@claude-code-skills
echo "  —  [joel-fin ] trading-operations"
run claude plugins disable trading-operations@JoelLewis-finance-skills
echo "  —  [joel-fin ] wealth-management"
run claude plugins disable wealth-management@JoelLewis-finance-skills
echo "  —  [official ] skill-creator"
run claude plugins disable skill-creator@claude-plugins-official
echo "  —  [py-back  ] python-typing"
run claude plugins disable python-typing@python-backend-plugins
echo "  —  [py-back  ] ruff-lint"
run claude plugins disable ruff-lint@python-backend-plugins
echo "  —  [workflow ] unit-testing"
run claude plugins disable unit-testing@claude-code-workflows
echo "  —  [skills   ] data-quality-auditor"
run claude plugins disable data-quality-auditor@claude-code-skills

# NEVER
echo "  🚫 [workflow ] blockchain-web3"
run claude plugins disable blockchain-web3@claude-code-workflows
echo "  🚫 [official ] superpowers"
run claude plugins disable superpowers@claude-plugins-official

# Agent Teams — ON (3 parallel teammates)
toggle_at "on"

echo ""
echo "✓ P5b done: 18 enabled | 23 disabled | 2 never"
echo "  Agent Teams: ON (3 teammates: backtesting, load+security, residency)"
echo "  Start: claude --dangerously-skip-permissions --model claude-opus-4-8"
echo ""
