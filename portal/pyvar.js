/* pyvar.js — pyvar.com shared components
   Completely separate from fibtec.co.uk */

// Dev CloudFront domain fronting the API — hardcoded the same way
// scripts/test_cold_start.sh and scripts/chaos_test.sh already do; swap
// once pyvar.com DNS (P8 Task 7) is wired up. Portal itself is not
// deployed anywhere yet, so this is the only real endpoint to call.
const API_BASE = 'https://d1mqqddh8gu2qi.cloudfront.net';

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
      <a href="index.html#get-api-key" class="nav-cta">Get API key</a>
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
// mean visitors routinely wait on a cold Spot ASG scale-up). See API_BASE
// above for why the domain is hardcoded.
const PUBLIC_DATA_BASE = `${API_BASE}/public`;

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

// ── Registration form (P8 Task 3) ─────────────────────────────────────────
// POSTs to /api/v1/auth/register. The response is identical whether the
// address is new, re-registering unverified, or already verified (see
// api/routes/auth.py) — this form never learns which, by design.
async function submitRegistration() {
  const input = document.getElementById('registerEmail');
  const statusEl = document.getElementById('registerStatus');
  const btn = document.getElementById('registerSubmit');
  if (!input || !statusEl || !btn) return;

  const email = input.value.trim();
  if (!email || !email.includes('@')) {
    statusEl.textContent = 'Enter a valid email address.';
    statusEl.className = 'get-key-status get-key-error';
    return;
  }

  btn.disabled = true;
  statusEl.textContent = 'Sending…';
  statusEl.className = 'get-key-status';
  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) throw new Error('request failed');
    statusEl.textContent = "Check your email for a verification link (if it doesn't arrive — no email transport is wired up yet in dev; ask an operator to check the API logs).";
    statusEl.className = 'get-key-status get-key-ok';
    input.value = '';
  } catch (e) {
    statusEl.textContent = 'Something went wrong — try again shortly.';
    statusEl.className = 'get-key-status get-key-error';
  } finally {
    btn.disabled = false;
  }
}

// ── Dashboard page (P8 Task 3) — dashboard.html only ──────────────────────
// Calls GET /api/v1/auth/verify?token=... and shows the issued JWT once.
async function renderDashboard() {
  const card = document.getElementById('dashCard');
  if (!card) return;

  const token = new URLSearchParams(window.location.search).get('token');
  if (!token) {
    card.innerHTML = '<div class="dash-title">No verification token</div>'
      + '<div class="dash-body dash-error">This page expects a <code>?token=</code> link from your verification email.</div>';
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/api/v1/auth/verify?token=${encodeURIComponent(token)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Verification failed');

    card.innerHTML = '<div class="dash-title">You\'re verified</div>'
      + '<div class="dash-body">Here\'s your API key (JWT), ' + data.tier + ' tier. It\'s shown once — copy it now.</div>'
      + '<div class="dash-token" id="dashToken"></div>'
      + '<span class="dash-copy" id="dashCopyBtn">copy</span>';
    document.getElementById('dashToken').textContent = data.access_token;
    const copyBtn = document.getElementById('dashCopyBtn');
    copyBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(data.access_token);
      copyBtn.textContent = 'copied!';
      setTimeout(() => { copyBtn.textContent = 'copy'; }, 1500);
    });
  } catch (e) {
    card.innerHTML = '<div class="dash-title">Verification failed</div>'
      + `<div class="dash-body dash-error">${(e && e.message) || 'The link may be invalid or expired.'} <a href="index.html#get-api-key">Register again</a>.</div>`;
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
