#!/bin/bash
# pyvar.com Phase P5 — UNIFIED v3
# Testing & Validation | Wk 14-18 | Agent Teams: ⚠️  CONDITIONAL
# Usage: ./phase-p5.sh [--dry-run|--status|--at-only]
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
echo "║ pyvar · P5: Testing & Validation                       ║"
echo "║ Wk 14-18   · Agent Teams: ⚠️  CONDITIONAL      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
# Full testing stack: pytest-assistant, scientific, ln-620-auditor, security.
# Agent Teams CONDITIONAL: safe for parallel domain validation reads only.
echo ""
[ $AT_ONLY -eq 1 ] && { toggle_at "on"; exit 0; }

# Install new plugins (idempotent)
install_if_missing "agent-orchestration@claude-code-workflows"
install_if_missing "commit-commands@claude-plugins-official"
install_if_missing "compliance@JoelLewis-finance-skills"
install_if_missing "context7@claude-plugins-official"
install_if_missing "data-analysis@K-Dense-AI-scientific-agent-skills"
install_if_missing "ln-620-codebase-auditor@levnikolaevich-skills-marketplace"
install_if_missing "pr-review-toolkit@claude-plugins-official"
install_if_missing "pytest-assistant@python-backend-plugins"
install_if_missing "ra-qm-skills@claude-code-skills"
install_if_missing "scientific-computing@K-Dense-AI-scientific-agent-skills"
install_if_missing "unit-testing@claude-code-workflows"

# ENABLE
echo "  ✅ [workflow ] agent-orchestration [WSHOBSON]"
run claude plugins enable agent-orchestration@claude-code-workflows
echo "  ✅ [workflow ] api-testing-observability"
run claude plugins enable api-testing-observability@claude-code-workflows
echo "  ✅ [skills   ] aws-architect"
run claude plugins enable aws-architect@claude-code-skills
echo "  ✅ [workflow ] cloud-infrastructure"
run claude plugins enable cloud-infrastructure@claude-code-workflows
echo "  ✅ [official ] commit-commands [ZIP-NEW]"
run claude plugins enable commit-commands@claude-plugins-official
echo "  ✅ [joel-fin ] compliance [ZIP-NEW]"
run claude plugins enable compliance@JoelLewis-finance-skills
echo "  ✅ [workflow ] comprehensive-review"
run claude plugins enable comprehensive-review@claude-code-workflows
echo "  ✅ [official ] context7 [ZIP-NEW]"
run claude plugins enable context7@claude-plugins-official
echo "  ✅ [sci-agent] data-analysis [ZIP-NEW]"
run claude plugins enable data-analysis@K-Dense-AI-scientific-agent-skills
echo "  ✅ [skills   ] data-quality-auditor"
run claude plugins enable data-quality-auditor@claude-code-skills
echo "  ✅ [skills   ] finance-skills"
run claude plugins enable finance-skills@claude-code-skills
echo "  ✅ [official ] github"
run claude plugins enable github@claude-plugins-official
echo "  ✅ [lev-skill] ln-620-codebase-auditor [ZIP-NEW]"
run claude plugins enable ln-620-codebase-auditor@levnikolaevich-skills-marketplace
echo "  ✅ [workflow ] performance-testing-review"
run claude plugins enable performance-testing-review@claude-code-workflows
echo "  ✅ [official ] pr-review-toolkit [ZIP-NEW]"
run claude plugins enable pr-review-toolkit@claude-plugins-official
echo "  ✅ [official ] pyright-lsp"
run claude plugins enable pyright-lsp@claude-plugins-official
echo "  ✅ [py-back  ] pytest-assistant [ZIP-NEW]"
run claude plugins enable pytest-assistant@python-backend-plugins
echo "  ✅ [workflow ] quantitative-trading"
run claude plugins enable quantitative-trading@claude-code-workflows
echo "  ✅ [skills   ] ra-qm-skills [ZIP-NEW]"
run claude plugins enable ra-qm-skills@claude-code-skills
echo "  ✅ [official ] ralph-loop"
run claude plugins enable ralph-loop@claude-plugins-official
echo "  ✅ [sci-agent] scientific-computing [ZIP-NEW]"
run claude plugins enable scientific-computing@K-Dense-AI-scientific-agent-skills
echo "  ✅ [workflow ] security-scanning"
run claude plugins enable security-scanning@claude-code-workflows
echo "  ✅ [skills   ] statistical-analyst"
run claude plugins enable statistical-analyst@claude-code-skills
echo "  ✅ [workflow ] unit-testing [WSHOBSON]"
run claude plugins enable unit-testing@claude-code-workflows

# DISABLE
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
echo "  —  [joel-fin ] core [ZIP-NEW]"
run claude plugins disable core@JoelLewis-finance-skills
echo "  —  [workflow ] data-engineering"
run claude plugins disable data-engineering@claude-code-workflows
echo "  —  [workflow ] database-cloud-optimization"
run claude plugins disable database-cloud-optimization@claude-code-workflows
echo "  —  [skills   ] docker-development"
run claude plugins disable docker-development@claude-code-skills
echo "  —  [workflow ] documentation-generation"
run claude plugins disable documentation-generation@claude-code-workflows
echo "  —  [official ] feature-dev [ZIP-NEW]"
run claude plugins disable feature-dev@claude-plugins-official
echo "  —  [official ] frontend-design"
run claude plugins disable frontend-design@claude-plugins-official
echo "  —  [workflow ] frontend-mobile-development"
run claude plugins disable frontend-mobile-development@claude-code-workflows
echo "  —  [skills   ] karpathy-coder"
run claude plugins disable karpathy-coder@claude-code-skills
echo "  —  [lev-skill] ln-100-documents-pipeline [ZIP-NEW]"
run claude plugins disable ln-100-documents-pipeline@levnikolaevich-skills-marketplace
echo "  —  [workflow ] python-development [WSHOBSON]"
run claude plugins disable python-development@claude-code-workflows
echo "  —  [py-back  ] python-typing [ZIP-NEW]"
run claude plugins disable python-typing@python-backend-plugins
echo "  —  [py-back  ] ruff-lint [ZIP-NEW]"
run claude plugins disable ruff-lint@python-backend-plugins
echo "  —  [official ] skill-creator"
run claude plugins disable skill-creator@claude-plugins-official
echo "  —  [skills   ] terraform-patterns"
run claude plugins disable terraform-patterns@claude-code-skills
echo "  —  [joel-fin ] trading-operations [ZIP-NEW]"
run claude plugins disable trading-operations@JoelLewis-finance-skills
echo "  —  [joel-fin ] wealth-management [ZIP-NEW]"
run claude plugins disable wealth-management@JoelLewis-finance-skills

# NEVER
echo "  🚫 [workflow ] blockchain-web3"
run claude plugins disable blockchain-web3@claude-code-workflows
echo "  🚫 [official ] superpowers"
run claude plugins disable superpowers@claude-plugins-official

# Agent Teams
toggle_at "on"

echo ""
echo "✓ P5 done: 24 enabled | 24 disabled | 2 never"
echo "  13 original | 2 wshobson | 9 zip-new | AT: ⚠️  CONDITIONAL"
echo "  Local SKILL.md files: always active (no toggle needed)"
echo "  Start: claude --model claude-opus-4-6"
echo ""
