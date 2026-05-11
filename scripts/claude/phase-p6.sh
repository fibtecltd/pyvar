#!/bin/bash
# pyvar.com Phase P6 — UNIFIED v3
# Usage Statistics & Observability | Wk 16-19 | Agent Teams: ❌ DISABLED
# Usage: ./phase-p6.sh [--dry-run|--status|--at-only]
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
json.dump(s,open(f,'w'),indent=2)" && echo "  🤝 Agent Teams ON  (restart: claude --model claude-opus-4-6)"
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
echo "║ pyvar · P6: Usage Statistics & Observability           ║"
echo "║ Wk 16-19   · Agent Teams: ❌ DISABLED           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
# Observability: metrics, dashboards, alarms. Sequential config ordering. AT OFF.
echo ""
# Install new plugins (idempotent)
install_if_missing "commit-commands@claude-plugins-official"
install_if_missing "context7@claude-plugins-official"
install_if_missing "data-analysis@K-Dense-AI-scientific-agent-skills"

# ENABLE
echo "  ✅ [workflow ] api-testing-observability"
run claude plugins enable api-testing-observability@claude-code-workflows
echo "  ✅ [skills   ] aws-architect"
run claude plugins enable aws-architect@claude-code-skills
echo "  ✅ [workflow ] cloud-infrastructure"
run claude plugins enable cloud-infrastructure@claude-code-workflows
echo "  ✅ [official ] commit-commands [ZIP-NEW]"
run claude plugins enable commit-commands@claude-plugins-official
echo "  ✅ [workflow ] comprehensive-review"
run claude plugins enable comprehensive-review@claude-code-workflows
echo "  ✅ [official ] context7 [ZIP-NEW]"
run claude plugins enable context7@claude-plugins-official
echo "  ✅ [sci-agent] data-analysis [ZIP-NEW]"
run claude plugins enable data-analysis@K-Dense-AI-scientific-agent-skills
echo "  ✅ [workflow ] data-engineering"
run claude plugins enable data-engineering@claude-code-workflows
echo "  ✅ [workflow ] database-cloud-optimization"
run claude plugins enable database-cloud-optimization@claude-code-workflows
echo "  ✅ [skills   ] docker-development"
run claude plugins enable docker-development@claude-code-skills
echo "  ✅ [official ] github"
run claude plugins enable github@claude-plugins-official
echo "  ✅ [official ] pyright-lsp"
run claude plugins enable pyright-lsp@claude-plugins-official
echo "  ✅ [official ] ralph-loop"
run claude plugins enable ralph-loop@claude-plugins-official
echo "  ✅ [skills   ] statistical-analyst"
run claude plugins enable statistical-analyst@claude-code-skills

# DISABLE
echo "  —  [workflow ] agent-orchestration [WSHOBSON]"
run claude plugins disable agent-orchestration@claude-code-workflows
echo "  —  [workflow ] api-scaffolding"
run claude plugins disable api-scaffolding@claude-code-workflows
echo "  —  [workflow ] application-performance"
run claude plugins disable application-performance@claude-code-workflows
echo "  —  [skills   ] autoresearch-agent [ZIP-NEW]"
run claude plugins disable autoresearch-agent@claude-code-skills
echo "  —  [workflow ] backend-development [WSHOBSON]"
run claude plugins disable backend-development@claude-code-workflows
echo "  —  [official ] claude-md-management"
run claude plugins disable claude-md-management@claude-plugins-official
echo "  —  [py-back  ] clean-code [ZIP-NEW]"
run claude plugins disable clean-code@python-backend-plugins
echo "  —  [workflow ] code-documentation"
run claude plugins disable code-documentation@claude-code-workflows
echo "  —  [joel-fin ] compliance [ZIP-NEW]"
run claude plugins disable compliance@JoelLewis-finance-skills
echo "  —  [joel-fin ] core [ZIP-NEW]"
run claude plugins disable core@JoelLewis-finance-skills
echo "  —  [skills   ] data-quality-auditor"
run claude plugins disable data-quality-auditor@claude-code-skills
echo "  —  [workflow ] documentation-generation"
run claude plugins disable documentation-generation@claude-code-workflows
echo "  —  [official ] feature-dev [ZIP-NEW]"
run claude plugins disable feature-dev@claude-plugins-official
echo "  —  [skills   ] finance-skills"
run claude plugins disable finance-skills@claude-code-skills
echo "  —  [official ] frontend-design"
run claude plugins disable frontend-design@claude-plugins-official
echo "  —  [workflow ] frontend-mobile-development"
run claude plugins disable frontend-mobile-development@claude-code-workflows
echo "  —  [skills   ] karpathy-coder"
run claude plugins disable karpathy-coder@claude-code-skills
echo "  —  [lev-skill] ln-100-documents-pipeline [ZIP-NEW]"
run claude plugins disable ln-100-documents-pipeline@levnikolaevich-skills-marketplace
echo "  —  [lev-skill] ln-620-codebase-auditor [ZIP-NEW]"
run claude plugins disable ln-620-codebase-auditor@levnikolaevich-skills-marketplace
echo "  —  [workflow ] performance-testing-review"
run claude plugins disable performance-testing-review@claude-code-workflows
echo "  —  [official ] pr-review-toolkit [ZIP-NEW]"
run claude plugins disable pr-review-toolkit@claude-plugins-official
echo "  —  [py-back  ] pytest-assistant [ZIP-NEW]"
run claude plugins disable pytest-assistant@python-backend-plugins
echo "  —  [workflow ] python-development [WSHOBSON]"
run claude plugins disable python-development@claude-code-workflows
echo "  —  [py-back  ] python-typing [ZIP-NEW]"
run claude plugins disable python-typing@python-backend-plugins
echo "  —  [workflow ] quantitative-trading"
run claude plugins disable quantitative-trading@claude-code-workflows
echo "  —  [skills   ] ra-qm-skills [ZIP-NEW]"
run claude plugins disable ra-qm-skills@claude-code-skills
echo "  —  [py-back  ] ruff-lint [ZIP-NEW]"
run claude plugins disable ruff-lint@python-backend-plugins
echo "  —  [sci-agent] scientific-computing [ZIP-NEW]"
run claude plugins disable scientific-computing@K-Dense-AI-scientific-agent-skills
echo "  —  [workflow ] security-scanning"
run claude plugins disable security-scanning@claude-code-workflows
echo "  —  [official ] skill-creator"
run claude plugins disable skill-creator@claude-plugins-official
echo "  —  [skills   ] terraform-patterns"
run claude plugins disable terraform-patterns@claude-code-skills
echo "  —  [joel-fin ] trading-operations [ZIP-NEW]"
run claude plugins disable trading-operations@JoelLewis-finance-skills
echo "  —  [workflow ] unit-testing [WSHOBSON]"
run claude plugins disable unit-testing@claude-code-workflows
echo "  —  [joel-fin ] wealth-management [ZIP-NEW]"
run claude plugins disable wealth-management@JoelLewis-finance-skills

# NEVER
echo "  🚫 [workflow ] blockchain-web3"
run claude plugins disable blockchain-web3@claude-code-workflows
echo "  🚫 [official ] superpowers"
run claude plugins disable superpowers@claude-plugins-official

# Agent Teams
toggle_at "off"

echo ""
echo "✓ P6 done: 14 enabled | 34 disabled | 2 never"
echo "  11 original | 0 wshobson | 3 zip-new | AT: ❌ DISABLED"
echo "  Local SKILL.md files: always active (no toggle needed)"
echo "  Start: claude"
echo ""
