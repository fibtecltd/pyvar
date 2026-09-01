/* pyvar.js — pyvar.com shared components
   Completely separate from fibtec.co.uk */

// task #44 -- was a hardcoded literal (dev's raw pre-cutover CloudFront
// domain, unconditionally) until every environment's portal called DEV's
// API regardless of which environment actually served the page. Empty
// string (relative path) instead: main.py mounts portal/ at "/" in the
// SAME FastAPI app that serves /api/v1/* and /public/*, and CloudFront
// (pyvar-cdk/stacks/edge_stack.py) has exactly one origin behind
// everything except /health and /docs -- so whatever domain served this
// script (pyvar.com, www.pyvar.com, dev.pyvar.com, or plain
// localhost:8000 in local dev) is always the correct API host too, in
// every environment, by construction. No per-environment value needed,
// unlike task #41/#43's fixes -- this can't drift out of sync again.
const API_BASE = '';

// ── pyvar logomark — waveform + terminal cursor ───────────────────
const LOGO_SVG = `<svg width="28" height="22" viewBox="0 0 28 22" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M1 16C3.5 16 4.5 10 7 10C9.5 10 10.5 16 13 16C15.5 16 16.5 10 19 4" stroke="#a84a2e" stroke-width="1.75" stroke-linecap="round"/>
  <rect x="21" y="14" width="6" height="2.5" rx="1" fill="#a84a2e" opacity="0.9">
    <animate attributeName="opacity" values="0.9;0.2;0.9" dur="1.2s" repeatCount="indefinite"/>
  </rect>
</svg>`;

function buildNav(active = 'home') {
  const links = [
    {id:'home',      label:'home',        href:'index.html'},
    {id:'domains',   label:'domains',     href:'index.html#domains'},
    {id:'api',       label:'api docs',    href:'index.html#api'},
    {id:'plugins',   label:'plugins',     href:'plugins.html'},
    {id:'github',    label:'github ↗',    href:'https://github.com/fibtecltd/pyvar', ext:true},
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
      <span class="nav-version" data-version>v0.1.2</span>
      <a href="https://fibtec.co.uk" target="_blank" class="nav-gh" title="Built by Fibtec Limited">by fibtec.co.uk</a>
      <a href="index.html#get-api-key" class="nav-cta">Get API key</a>
    </div>
  </nav>`;
}

const FOOTER_LOGO = `<svg width="32" height="26" viewBox="0 0 28 22" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M1 16C3.5 16 4.5 10 7 10C9.5 10 10.5 16 13 16C15.5 16 16.5 10 19 4" stroke="#a84a2e" stroke-width="1.75" stroke-linecap="round"/>
  <rect x="21" y="14" width="6" height="2.5" rx="1" fill="#a84a2e" opacity="0.7"/>
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
          <p class="footer-tagline">Open-source financial and risk computation platform. 385 functions across 8 domains. Free to use.</p>
          <div class="footer-meta">
            <span>Built by <a href="https://fibtec.co.uk" target="_blank">Fibtec Limited</a> · UK</span>
            <a href="https://github.com/fibtecltd/pyvar" target="_blank">github.com/fibtecltd/pyvar ↗</a>
            <a href="mailto:info@pyvar.com">info@pyvar.com</a>
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
              <a href="plugins.html">Claude Code plugins</a>
              <a href="#">Python SDK</a>
              <a href="https://github.com/fibtecltd/pyvar" target="_blank">GitHub ↗</a>
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
// mean visitors routinely wait on a cold Spot ASG scale-up).
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

async function initVersion() {
  // [data-version] appears on every page (buildNav's nav-version span) plus
  // index.html's own hero eyebrow -- hydrated from the same status.json
  // fetch initStatusIndicator uses, so this can't drift from the actually
  // published pyvar-client version the way a hardcoded literal did before
  // (see pyvar-cdk/lambda/public_data_publisher/handler.py's own comment).
  const els = document.querySelectorAll('[data-version]');
  if (!els.length) return;
  try {
    const res = await fetch(`${PUBLIC_DATA_BASE}/status.json`, { cache: 'no-store' });
    if (!res.ok) return; // leave the static fallback version in place
    const data = await res.json();
    if (!data.pyvar_client_version) return; // PyPI outage carried no prior value either
    els.forEach(el => { el.textContent = `v${data.pyvar_client_version}`; });
  } catch (e) {
    // Offline / pre-deploy / CORS — static fallback version already shown.
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
    // Show the API's own message (schemas/auth.py::RegisterResponse) rather
    // than a hardcoded guess — it was previously a leftover dev-only string
    // ("no email transport is wired up yet in dev...") shown verbatim in
    // prod regardless of whether the email actually sent, which masked a
    // real prod delivery failure instead of surfacing it.
    const data = await res.json().catch(() => ({}));
    statusEl.textContent =
      data.message || "Check your email for a verification link.";
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

    // Also stored for the "Try it" panels (P8 Task 5) on domain pages, so a
    // visitor who verified once doesn't have to re-paste their key per function.
    localStorage.setItem('pyvar_jwt', data.access_token);

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
    // e.message can trace back to window.location.search (the ?token=...
    // this function reads above) via the fetch URL and any error text a
    // browser or server derives from it -- escape before reinterpreting as
    // HTML, same rule as the comment above _escapeHtml() states for API
    // response text.
    const safeMessage = _escapeHtml((e && e.message) || 'The link may be invalid or expired.');
    card.innerHTML = '<div class="dash-title">Verification failed</div>'
      + `<div class="dash-body dash-error">${safeMessage} <a href="index.html#get-api-key">Register again</a>.</div>`;
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

// ── Domain function grid + "Try it" panel (P8 Task 5) ─────────────────────
// One shared renderer for all 8 domain pages, reading portal/functions.json
// — replaces each page's own hardcoded FUNCTIONS/ALL_FNS array. Those arrays
// had drifted badly (domain-market-risk.html was showing credit-risk's
// content verbatim — #152 — and domain-alm.html's had no descriptions and
// scrambled category tags); rendering every domain from the one generated,
// code-derived source fixes that as a side effect and gives every page a
// working "Try it" panel and working search-result anchors (Task 4's
// results link to {domain_page}#{function_name} — this renderer is what
// gives each fn-card that id).
async function initDomainGrid(domainSlug) {
  const grid = document.getElementById('fnGrid');
  if (!grid) return;

  const all = await fetch('functions.json').then(r => r.json());
  const items = all.filter(f => f.domain === domainSlug);
  const countLbl = document.getElementById('countLbl');
  const filterInput = document.getElementById('fnFilter');

  function render(filterText) {
    const q = (filterText || '').trim().toLowerCase();
    const shown = q
      ? items.filter(f => f.display_name.toLowerCase().includes(q) || (f.summary || '').toLowerCase().includes(q))
      : items;
    if (countLbl) {
      countLbl.textContent = q
        ? `Showing ${shown.length} of ${items.length} functions`
        : `Showing all ${items.length} functions`;
    }
    grid.innerHTML = shown.map((f, i) => `
      <div class="fn-card" id="${f.name}" data-fn="${f.name}" style="animation-delay:${i * 0.02}s" role="button" tabindex="0" aria-label="Try ${f.display_name}">
        <div class="fn-name">${f.display_name}</div>
        <div class="fn-desc">${f.summary}</div>
        <div class="fn-try">Try it →</div>
      </div>
    `).join('');
  }

  render('');
  if (filterInput) filterInput.addEventListener('input', () => render(filterInput.value));

  function activateCard(card) {
    const fn = items.find(f => f.name === card.dataset.fn);
    if (fn) openTryItPanel(fn, card);
  }

  grid.addEventListener('click', e => {
    const card = e.target.closest('.fn-card');
    if (!card) return;
    activateCard(card);
  });

  grid.addEventListener('keydown', e => {
    const card = e.target.closest('.fn-card');
    if (!card) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault(); // ' ' would otherwise scroll the page
      activateCard(card);
    }
  });

  // Deep-link from a search result: index.html search -> domain_page#function_name
  if (window.location.hash) {
    const fn = items.find(f => f.name === window.location.hash.slice(1));
    if (fn) {
      setTimeout(() => {
        const el = document.getElementById(fn.name);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        openTryItPanel(fn, el);
      }, 150);
    }
  }
}

// API responses and error details can echo back untrusted request input
// (e.g. a Pydantic validation message quoting the invalid value submitted) —
// escape before inserting via innerHTML so it can never be parsed as markup.
function _escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _tryitFieldHtml(p) {
  const label = `${p.name}${p.required ? ' *' : ''}`;
  const attr = `data-param="${p.name}"`;
  if (p.type === 'boolean') {
    return `<label class="tryit-field"><span>${label}</span><input type="checkbox" ${attr} ${p.default ? 'checked' : ''}/></label>`;
  }
  if (p.type === 'integer' || p.type === 'number') {
    const bounds = [
      p.minimum != null ? `min="${p.minimum}"` : '',
      p.maximum != null ? `max="${p.maximum}"` : '',
      p.type === 'integer' ? 'step="1"' : 'step="any"',
    ].join(' ');
    const value = p.default != null ? p.default : '';
    return `<label class="tryit-field"><span>${label}</span><input type="number" ${bounds} ${attr} value="${value}"/></label>`;
  }
  if (p.type === 'array' || p.type === 'object') {
    const placeholder = p.type === 'array' ? 'e.g. [0.01, -0.02, 0.015]' : 'e.g. {"key": 1.0}';
    return `<label class="tryit-field tryit-field-wide"><span>${label}</span><textarea ${attr} placeholder="${placeholder}" rows="3"></textarea></label>`;
  }
  const value = p.default != null ? p.default : '';
  return `<label class="tryit-field"><span>${label}</span><input type="text" ${attr} value="${value}"/></label>`;
}

let _tryitTrigger = null;

// ── Formula rendering (P11 item 5) ──────────────────────────────────────────
// KaTeX is vendored (portal/vendor/katex/), not CDN-loaded -- same
// self-contained-dependency convention as vendor/fuse.min.js. Lazy-loaded
// only when a Try-it panel for a function that actually has a formula is
// opened, so a page where a visitor never opens one never pays for it.
let _katexLoadPromise = null;

function _ensureKatex() {
  if (_katexLoadPromise) return _katexLoadPromise;
  if (typeof katex !== 'undefined') {
    _katexLoadPromise = Promise.resolve();
    return _katexLoadPromise;
  }
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'vendor/katex/katex.min.css';
  document.head.appendChild(link);
  _katexLoadPromise = _loadScript('vendor/katex/katex.min.js');
  return _katexLoadPromise;
}

function _formulaBlockHtml(fn) {
  if (!fn.formula || !fn.formula.formula_latex) return '';
  return '<div class="tryit-formula" id="tryitFormula"></div>';
}

async function _renderFormula(fn) {
  const el = document.getElementById('tryitFormula');
  if (!el || !fn.formula || !fn.formula.formula_latex) return;
  await _ensureKatex();
  const f = fn.formula;
  let html;
  try {
    html = `<div class="tryit-formula-katex">${katex.renderToString(f.formula_latex, { throwOnError: false, displayMode: true })}</div>`;
  } catch (e) {
    return; // malformed LaTeX -- fail silently rather than break the panel
  }
  const legendEntries = Object.entries(f.symbol_map || {});
  if (legendEntries.length) {
    html += '<div class="tryit-formula-legend">' + legendEntries.map(([param, symbol]) => {
      let symbolHtml = _escapeHtml(symbol);
      try { symbolHtml = katex.renderToString(symbol, { throwOnError: false }); } catch (e) { /* fall back to escaped text above */ }
      return `<span class="tryit-formula-legend-item">${symbolHtml} = ${_escapeHtml(param)}</span>`;
    }).join('') + '</div>';
  }
  if (f.citation) {
    html += `<div class="tryit-formula-citation">${_escapeHtml(f.citation)}</div>`;
  }
  if (f.caveat) {
    html += `<div class="tryit-formula-caveat">⚠ ${_escapeHtml(f.caveat)}</div>`;
  }
  el.innerHTML = html;
}

function closeTryItPanel() {
  const panel = document.getElementById('tryitPanel');
  if (panel) panel.classList.remove('open');
  if (_tryitTrigger) { _tryitTrigger.focus(); _tryitTrigger = null; }
}

function openTryItPanel(fn, triggerEl) {
  _tryitTrigger = triggerEl || null;
  let panel = document.getElementById('tryitPanel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'tryitPanel';
    panel.className = 'tryit-overlay';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    document.body.appendChild(panel);
    panel.addEventListener('click', e => { if (e.target === panel) closeTryItPanel(); });
    document.addEventListener('keydown', e => {
      if (!panel.classList.contains('open')) return;
      if (e.key === 'Escape') { closeTryItPanel(); return; }
      if (e.key !== 'Tab') return;
      // Trap focus inside the panel while it's open (WAI-ARIA modal dialog pattern)
      const focusable = panel.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    });
  }
  panel.setAttribute('aria-label', `Try ${fn.display_name}`);

  const storedToken = localStorage.getItem('pyvar_jwt') || '';
  panel.innerHTML = `
    <div class="tryit-card" style="--rc:${fn.domain_color}">
      <div class="tryit-header">
        <div>
          <div class="tryit-domain">${fn.domain_label}</div>
          <div class="tryit-title">${fn.display_name}</div>
        </div>
        <button type="button" class="tryit-close" id="tryitClose" aria-label="Close try-it panel">Esc</button>
      </div>
      <div class="tryit-desc">${fn.summary}${fn.description ? ' — ' + fn.description.replace(/\n/g, ' ') : ''}</div>
      ${_formulaBlockHtml(fn)}
      <div class="tryit-jwt-row">
        <input type="text" id="tryitJwt" class="tryit-jwt-input" placeholder="Paste your API key (JWT)…" value="${storedToken}"/>
        <a href="index.html#get-api-key" class="tryit-jwt-link">Get a free key →</a>
      </div>
      <form id="tryitForm" class="tryit-form">
        ${fn.params.map(_tryitFieldHtml).join('')}
        <button type="submit" class="btn-green tryit-submit">Run →</button>
      </form>
      <div id="tryitResult" class="tryit-result"></div>
    </div>
  `;
  panel.classList.add('open');
  document.getElementById('tryitClose').addEventListener('click', closeTryItPanel);
  document.getElementById('tryitForm').addEventListener('submit', e => _submitTryIt(e, fn));
  document.getElementById('tryitJwt').focus();
  _renderFormula(fn);
}

async function _submitTryIt(e, fn) {
  e.preventDefault();
  const resultEl = document.getElementById('tryitResult');
  const token = document.getElementById('tryitJwt').value.trim();
  if (!token) {
    resultEl.innerHTML = '<div class="tryit-error">Paste an API key above, or <a href="index.html#get-api-key">get one free</a>.</div>';
    return;
  }
  localStorage.setItem('pyvar_jwt', token);

  const body = {};
  let parseError = '';
  for (const p of fn.params) {
    const field = document.querySelector(`[data-param="${p.name}"]`);
    if (!field) continue;
    if (p.type === 'boolean') { body[p.name] = field.checked; continue; }
    const raw = field.value.trim();
    if (!raw) continue;
    if (p.type === 'number' || p.type === 'integer') { body[p.name] = Number(raw); continue; }
    if (p.type === 'array' || p.type === 'object') {
      try { body[p.name] = JSON.parse(raw); }
      catch (err) { parseError = `Invalid JSON in "${p.name}".`; break; }
      continue;
    }
    body[p.name] = raw;
  }
  if (parseError) {
    resultEl.innerHTML = `<div class="tryit-error">${parseError}</div>`;
    return;
  }

  resultEl.innerHTML = '<div class="tryit-pending">Running…</div>';
  try {
    const res = await fetch(`${API_BASE}${fn.path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    resultEl.innerHTML = `<pre class="tryit-json">${_escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
  } catch (err) {
    resultEl.innerHTML = `<div class="tryit-error">${_escapeHtml((err && err.message) || 'Request failed.')}</div>`;
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
      ? 'rgba(168,74,46,0.12)' : 'rgba(31,30,29,0.06)';
  }, { passive: true });
}

document.addEventListener('DOMContentLoaded', () => {
  initReveal(); initNav(); initStatusIndicator(); initTerminalDemo(); initSearch(); initVersion();
});
