/* pyvar.js — pyvar.com shared components
   Completely separate from fibtec.co.uk */

// ── pyvar logomark — waveform + terminal cursor ───────────────────
const LOGO_SVG = `<svg width="28" height="22" viewBox="0 0 28 22" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M1 16C3.5 16 4.5 10 7 10C9.5 10 10.5 16 13 16C15.5 16 16.5 10 19 4" stroke="#00d97e" stroke-width="1.75" stroke-linecap="round"/>
  <rect x="21" y="14" width="6" height="2.5" rx="1" fill="#00d97e" opacity="0.9">
    <animate attributeName="opacity" values="0.9;0.2;0.9" dur="1.2s" repeatCount="indefinite"/>
  </rect>
</svg>`;

function buildNav(active = 'home') {
  const links = [
    {id:'home',      label:'home',        href:'index.html'},
    {id:'domains',   label:'domains',     href:'index.html#domains'},
    {id:'api',       label:'api docs',    href:'index.html#api'},
    {id:'github',    label:'github ↗',    href:'https://github.com/fibtec-limited/pyvar', ext:true},
  ];
  return `<nav class="nav" id="mainNav">
    <a href="index.html" class="nav-logo">
      ${LOGO_SVG}
      <div class="nav-logo-domain">py<span>var</span>.com</div>
    </a>
    <div class="nav-links">
      ${links.map(l=>`<a href="${l.href}"${l.ext?' target="_blank"':''}${l.id===active?' class="active"':''}>${l.label}</a>`).join('')}
    </div>
    <div class="nav-right">
      <span class="nav-version">v0.1.0-beta</span>
      <a href="https://fibtec.co.uk" target="_blank" class="nav-gh" title="Built by Fibtec Limited">by fibtec.co.uk</a>
      <a href="index.html#api" class="nav-cta">Get API key</a>
    </div>
  </nav>`;
}

const FOOTER_LOGO = `<svg width="32" height="26" viewBox="0 0 28 22" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M1 16C3.5 16 4.5 10 7 10C9.5 10 10.5 16 13 16C15.5 16 16.5 10 19 4" stroke="#00d97e" stroke-width="1.75" stroke-linecap="round"/>
  <rect x="21" y="14" width="6" height="2.5" rx="1" fill="#00d97e" opacity="0.7"/>
</svg>`;

function buildFooter() {
  return `<footer class="footer">
    <div class="container">
      <div class="footer-inner">
        <div>
          <div class="footer-logo-wrap">
            <a href="index.html" style="display:flex;align-items:center;gap:10px">
              ${FOOTER_LOGO}
              <div style="font-family:var(--mono);font-size:18px;font-weight:600;color:var(--text)">py<span style="color:var(--green)">var</span>.com</div>
            </a>
          </div>
          <p class="footer-tagline">Open-source financial and risk computation platform. 382 regulatory-grade functions. Free forever.</p>
          <div class="footer-meta">
            <span>Built by <a href="https://fibtec.co.uk" target="_blank">Fibtec Limited</a> · UK</span>
            <a href="https://github.com/fibtec-limited/pyvar" target="_blank">github.com/fibtec-limited/pyvar ↗</a>
            <a href="mailto:info@fibtec.co.uk">info@fibtec.co.uk</a>
          </div>
        </div>
        <div class="footer-nav">
          <div>
            <div class="footer-col-title">Domains</div>
            <div class="footer-col-links">
              <a href="domain-market-risk.html">Market Risk</a>
              <a href="domain-credit-risk.html">Credit Risk</a>
              <a href="domain-liquidity-risk.html">Liquidity Risk</a>
              <a href="domain-operational-risk.html">Operational Risk</a>
              <a href="domain-portfolio-analytics.html">Portfolio Analytics</a>
            </div>
          </div>
          <div>
            <div class="footer-col-title">More domains</div>
            <div class="footer-col-links">
              <a href="domain-regulatory.html">Regulatory</a>
              <a href="domain-derivatives.html">Derivatives</a>
              <a href="domain-alm.html">ALM</a>
            </div>
          </div>
          <div>
            <div class="footer-col-title">Developers</div>
            <div class="footer-col-links">
              <a href="index.html#api">API reference</a>
              <a href="#">Python SDK</a>
              <a href="https://github.com/fibtec-limited/pyvar" target="_blank">GitHub ↗</a>
              <a href="#">Changelog</a>
            </div>
          </div>
          <div>
            <div class="footer-col-title">Company</div>
            <div class="footer-col-links">
              <a href="https://fibtec.co.uk" target="_blank">fibtec.co.uk ↗</a>
              <a href="https://fibtec.co.uk#contact" target="_blank">Enterprise support</a>
              <a href="#">Licence (MIT)</a>
              <a href="#">Contributing</a>
            </div>
          </div>
        </div>
      </div>
      <div class="footer-bottom">
        <div class="footer-copy">© 2026 Fibtec Limited · pyvar.com is MIT licensed · fibtec.co.uk</div>
        <div class="footer-legal">
          <a href="#">Privacy</a><a href="#">Terms</a><a href="#">MIT Licence</a>
        </div>
      </div>
    </div>
  </footer>`;
}

// ── Homepage: live status + terminal demo (P8 Task 1/2) ──────────────────
// Both status.json and demo-result.json are written every ~15min by a
// scheduled Lambda (pyvar-cdk/stacks/public_data_stack.py), not computed
// live per page visit — see that stack's module docstring for why (compute
// workers scale to zero; a real live call on every homepage load would
// mean visitors routinely wait on a cold Spot ASG scale-up). The dev
// CloudFront domain is hardcoded here the same way scripts/test_cold_start.sh
// and scripts/chaos_test.sh already do; swap once pyvar.com DNS (P8 Task 7)
// is wired up.
const PUBLIC_DATA_BASE = 'https://d1mqqddh8gu2qi.cloudfront.net/public';

function fmtGBP(n) {
  return '£' + Math.round(n).toLocaleString('en-GB');
}

async function initStatusIndicator() {
  const pill = document.querySelector('.status-pill');
  if (!pill) return;
  const labels = { operational: 'All systems operational', degraded: 'Degraded performance', down: 'Service disruption' };
  const colors = { operational: 'status-green', degraded: 'status-amber', down: 'status-red' };
  try {
    const res = await fetch(`${PUBLIC_DATA_BASE}/status.json`, { cache: 'no-store' });
    if (!res.ok) return; // leave the static default pill in place
    const data = await res.json();
    pill.classList.remove('status-green', 'status-amber', 'status-red');
    pill.classList.add(colors[data.status] || 'status-green');
    pill.textContent = labels[data.status] || labels.operational;
  } catch (e) {
    // Offline / pre-deploy / CORS — static default already shown, nothing to do.
  }
}

async function initTerminalDemo() {
  const body = document.querySelector('.terminal-body');
  if (!body) return;
  const nSimEl = body.querySelector('[data-demo="n_simulations"]');
  const varEl = body.querySelector('[data-demo="var_abs"]');
  const varNoteEl = body.querySelector('[data-demo="var_note"]');
  const cvarEl = body.querySelector('[data-demo="cvar_abs"]');
  const cvarNoteEl = body.querySelector('[data-demo="cvar_note"]');
  const runtimeEl = body.querySelector('[data-demo="runtime_ms"]');
  const runtimeNoteEl = body.querySelector('[data-demo="runtime_note"]');
  if (!varEl) return; // not the homepage terminal — nothing to hydrate

  try {
    const res = await fetch(`${PUBLIC_DATA_BASE}/demo-result.json`, { cache: 'no-store' });
    if (!res.ok) return; // leave the static illustrative example in place
    const data = await res.json();
    const nSim = data.request.n_simulations;
    const confidencePct = Math.round(data.request.confidence_level * 100);

    if (nSimEl) nSimEl.textContent = nSim.toLocaleString('en-GB');
    varEl.textContent = data.result.var_abs.toFixed(1);
    if (varNoteEl) varNoteEl.textContent = `# ${fmtGBP(data.result.var_abs)} (${confidencePct}% VaR)`;
    cvarEl.textContent = data.result.cvar_abs.toFixed(1);
    if (cvarNoteEl) cvarNoteEl.textContent = `# ${fmtGBP(data.result.cvar_abs)} (CVaR/ES)`;
    if (runtimeEl) runtimeEl.textContent = data.runtime_ms;
    if (runtimeNoteEl) {
      runtimeNoteEl.textContent = `# ${nSim.toLocaleString('en-GB')} paths · ${(data.runtime_ms / 1000).toFixed(1)}s`;
    }
  } catch (e) {
    // Offline / pre-deploy / CORS — static illustrative example already shown.
  }
}

function initReveal() {
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) e.target.classList.add('in'); });
  }, { threshold: 0.06 });
  document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
}

function initNav() {
  const nav = document.getElementById('mainNav');
  if (!nav) return;
  window.addEventListener('scroll', () => {
    nav.style.borderBottomColor = window.scrollY > 20
      ? 'rgba(0,217,126,0.12)' : 'rgba(255,255,255,0.06)';
  }, { passive: true });
}

document.addEventListener('DOMContentLoaded', () => {
  initReveal(); initNav(); initStatusIndicator(); initTerminalDemo();
});
