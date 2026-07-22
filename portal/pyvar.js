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
      <button type="button" class="nav-search-btn" id="navSearchBtn" aria-haspopup="dialog">Search <kbd>/</kbd></button>
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

// ── Search (P8 Task 4) ─────────────────────────────────────────────────────
// Fuse.js + portal/functions.json (scripts/generate_function_catalog.py) —
// one shared data source across all 385 functions, no per-function HTML.
// Both fuse.min.js and functions.json are loaded lazily, on first open, so
// pages where a visitor never searches never pay for either fetch.
let _searchState = null; // { fuse, functions } once loaded, else null

function _loadScript(src) {
  return new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = src;
    el.onload = resolve;
    el.onerror = () => reject(new Error(`failed to load ${src}`));
    document.head.appendChild(el);
  });
}

async function _ensureSearchIndex() {
  if (_searchState) return _searchState;
  const [, functions] = await Promise.all([
    typeof Fuse === 'undefined' ? _loadScript('vendor/fuse.min.js') : Promise.resolve(),
    fetch('functions.json').then(r => r.json()),
  ]);
  // description is deliberately excluded: it's long prose, and fuzzy-matching
  // short queries against it tanks precision (e.g. "var" matched 347/385
  // functions in testing). display_name/summary/domain give tighter, still
  // well under the 50ms target (measured 1-8ms locally over all 385 records).
  const fuse = new Fuse(functions, {
    keys: [
      { name: 'display_name', weight: 0.5 },
      { name: 'summary', weight: 0.3 },
      { name: 'domain_label', weight: 0.2 },
    ],
    threshold: 0.3,
    ignoreLocation: true,
    minMatchCharLength: 2,
  });
  _searchState = { fuse, functions };
  return _searchState;
}

function _renderSearchResults(matches) {
  const el = document.getElementById('searchResults');
  if (!matches.length) {
    el.innerHTML = '<div class="search-empty">No functions match.</div>';
    return;
  }
  el.innerHTML = matches.slice(0, 30).map(({ item }) => `
    <a class="search-result" style="--rc:${item.domain_color}" href="${item.domain_page}#${item.name}">
      <div class="search-result-top">
        <span class="search-result-domain">${item.domain_label}</span>
        <span class="search-result-name">${item.display_name}</span>
      </div>
      <div class="search-result-summary">${item.summary}</div>
    </a>
  `).join('');
}

function initSearch() {
  const btn = document.getElementById('navSearchBtn');
  if (!btn) return;

  const overlay = document.createElement('div');
  overlay.className = 'search-overlay';
  overlay.id = 'searchOverlay';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-label', 'Search functions');
  overlay.innerHTML = `
    <div class="search-panel">
      <div class="search-input-row">
        <input type="text" id="searchInput" class="search-input" placeholder="Search 385 functions across 8 domains…" autocomplete="off"/>
        <button type="button" class="search-close" id="searchClose" aria-label="Close search">Esc</button>
      </div>
      <div class="search-results" id="searchResults"></div>
    </div>
  `;
  document.body.appendChild(overlay);

  const input = document.getElementById('searchInput');
  const closeBtn = document.getElementById('searchClose');

  async function open() {
    overlay.classList.add('open');
    input.value = '';
    document.getElementById('searchResults').innerHTML = '';
    input.focus();
    await _ensureSearchIndex(); // pre-warm — first keystroke shouldn't pay fetch latency
  }
  function close() {
    overlay.classList.remove('open');
    btn.focus();
  }

  btn.addEventListener('click', open);
  closeBtn.addEventListener('click', close);
  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

  input.addEventListener('input', async () => {
    const query = input.value.trim();
    if (!query) {
      document.getElementById('searchResults').innerHTML = '';
      return;
    }
    const { fuse } = await _ensureSearchIndex();
    const results = fuse.search(query);
    _renderSearchResults(results);
  });

  document.addEventListener('keydown', e => {
    const isOpen = overlay.classList.contains('open');
    const typingElsewhere = ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName) && document.activeElement !== input;
    if (!isOpen && e.key === '/' && !typingElsewhere) {
      e.preventDefault();
      open();
    } else if (isOpen && e.key === 'Escape') {
      close();
    }
  });
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
  initReveal(); initNav(); initStatusIndicator(); initTerminalDemo(); initSearch();
});
