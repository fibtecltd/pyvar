// pyvar portal assistant, typed questions: the "Ask about this function" box in a function's Try-it panel.
//
// What it is: a text box under the three fixed buttons of portal/assistant.js. Unlike that file, which sends nothing,
// this one sends what the visitor types, and only when they press Ask: one POST to /api/v1/assistant/ask with the
// question (1 to 500 characters), the name of the function whose panel is open and up to three earlier turns of this
// conversation. Nothing is sent when the page loads, when the panel opens or while the visitor types. The server
// removes anything that looks like an e-mail address, key or token, gives the rest to Anthropic's Claude, checks
// the answer and replies (api/assistant/, assistant/guardrails.py). The privacy policy (section 5) and the terms
// (section 6) describe this, and the note under the box says it in the visitor's own words.
//
// Loading: pyvar.js adds this script only when GET /public/config says assistant_typed_enabled is true (the route
// is switched on in that environment). pyvar.js leaves an empty <div id="assistantTypedSlot" data-fn="<function>">
// in each Try-it panel and fires `pyvar:tryit-open`; this file fills that slot. If the route is closed to the
// visitor (switched off, an allowlist they are not on, a spend limit, a quota) the server's own fixed message is
// shown as text, and the buttons above keep working.
//
// Credential: whatever is in the panel's key box (#tryitJwt, a session token or a pyvar_ key) goes as a Bearer
// header, so a signed-in visitor is counted as themselves; with the box empty the visitor asks anonymously. Nothing
// is kept: the earlier turns live in this panel's memory only, never in storage, a cookie or the URL.
//
// Safety: everything from the server is put in the page with textContent / createTextNode, never as HTML. This file
// must not use innerHTML, eval, document.write or inline event handlers, and must not touch any storage
// (tests/test_assistant_typed_widget.py scans for them and runs the code under node).
(function () {
  'use strict';

  var ENDPOINT = '/api/v1/assistant/ask';
  var QUESTION_MAX = 500;   // schemas/assistant.py QUESTION_MAX
  var ANSWER_MAX = 1500;    // ... ANSWER_MAX: what an earlier answer may be when it goes back as history
  var HISTORY_MAX = 3;      // ... HISTORY_MAX
  var TIMEOUT_MS = 40000;   // the server stops a question at 30 seconds
  var NAME_OK = /^[A-Za-z0-9_]+$/;
  var TOKEN_OK = /^[A-Za-z0-9._~+\/=-]{1,4096}$/;
  var NOTE = 'Your question, up to three earlier turns of this conversation and this function\u2019s name are sent ' +
    'to Anthropic\u2019s Claude after we remove anything that looks like an e-mail address, key or token. Nothing ' +
    'from your computations or your account is sent, and a sample of answers is read by a second model to check ' +
    'them. Do not type personal or confidential information. Answers can be wrong: check them against the ' +
    'documentation. See the ';
  var GENERIC = 'The assistant is not available right now.';
  var HINT = 'The buttons above still work, and every function is listed on the home page.';

  var counter = 0;

  function make(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  // `code` spans (backticks) become <code> and **bold** becomes <strong>; everything else is plain text.
  // A ** without its partner stays as it was written. (The same rule as portal/assistant.js.)
  function inline(parent, line) {
    line.split('`').forEach(function (part, index) {
      if (part === '') return;
      if (index % 2 === 1) {
        parent.appendChild(make('code', 'assistant-code', part));
        return;
      }
      var pieces = part.split('**');
      if (pieces.length % 2 === 0) {
        parent.appendChild(document.createTextNode(part));
        return;
      }
      pieces.forEach(function (piece, i) {
        if (piece === '') return;
        if (i % 2 === 1) parent.appendChild(make('strong', '', piece));
        else parent.appendChild(document.createTextNode(piece));
      });
    });
  }

  // Paragraphs, and "- " lines as a list. Plain text in, DOM nodes out.
  function paragraphs(target, text) {
    var list = null;
    text.split('\n').forEach(function (raw) {
      var line = raw.trim();
      if (line === '') { list = null; return; }
      var bullet = /^[-*\u2022]\s+(.*)$/.exec(line);
      if (bullet) {
        if (!list) { list = make('ul', 'assistant-list'); target.appendChild(list); }
        var item = make('li');
        inline(item, bullet[1]);
        list.appendChild(item);
      } else {
        list = null;
        var p = make('p', 'assistant-text');
        inline(p, line);
        target.appendChild(p);
      }
    });
  }

  // The part of a 200 reply the box shows, or null if it is not what the route sends.
  function validate(data) {
    if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
    if (typeof data.answer !== 'string' || data.answer.trim() === '') return null;
    if (data.source !== 'live' && data.source !== 'static') return null;
    var clean = { answer: data.answer, source: data.source, functions: [], example: null };
    if (Array.isArray(data.functions)) {
      data.functions.forEach(function (name) {
        if (typeof name === 'string' && NAME_OK.test(name) && clean.functions.length < 6) clean.functions.push(name);
      });
    }
    var sp = data.suggested_parameters;
    if (sp && typeof sp === 'object' && !Array.isArray(sp) && typeof sp.function === 'string' &&
        NAME_OK.test(sp.function) && sp.values && typeof sp.values === 'object' && !Array.isArray(sp.values)) {
      clean.example = { fn: sp.function, text: JSON.stringify(sp.values, null, 2).slice(0, 4000) };
    }
    return clean;
  }

  // What to tell the visitor for a reply that is not a 200. Only fixed text of ours, or the fixed message the
  // server itself sends with a 503, ever reaches the page.
  function problem(status, data, retry) {
    var detail = data && typeof data === 'object' ? data.detail : null;
    if (status === 401) {
      return ['Your key was not accepted.', 'Clear the key box above to ask as a visitor, or get a new key.'];
    }
    if (status === 422) return ['That question could not be sent.', 'Use between 1 and ' + QUESTION_MAX + ' characters.'];
    if (status === 429) {
      var when = '';
      if (retry > 0) {
        var n = retry < 3600 ? Math.max(1, Math.ceil(retry / 60)) : Math.ceil(retry / 3600);
        when = ' in about ' + n + (retry < 3600 ? ' minute' : ' hour') + (n === 1 ? '' : 's');
      }
      return ['You have reached the limit for questions.', 'Try again' + when + '. The buttons above still work.'];
    }
    if (status === 503 && detail && typeof detail === 'object' && typeof detail.message === 'string') {
      var hint = typeof detail.hint === 'string' ? detail.hint : HINT;
      return [detail.message.slice(0, 300), hint.slice(0, 300)];
    }
    return [GENERIC, HINT];
  }

  function readToken() {
    var field = document.getElementById('tryitJwt');
    var value = field && typeof field.value === 'string' ? field.value.trim() : '';
    return TOKEN_OK.test(value) ? value : '';
  }

  function build(slot, name) {
    counter += 1;
    var id = 'assistant-typed-' + counter;
    var history = [];
    var busy = false;

    var root = make('section', 'assistant assistant-typed');
    root.setAttribute('aria-labelledby', id + '-title');
    root.appendChild(make('h3', 'assistant-title', 'Ask about this function')).id = id + '-title';

    var form = make('form', 'assistant-typed-form');
    form.setAttribute('novalidate', 'novalidate');
    var label = make('label', 'assistant-sr', 'Your question');
    label.htmlFor = id + '-q';
    var input = make('textarea', 'assistant-typed-input');
    input.id = id + '-q';
    input.rows = 3;
    input.maxLength = QUESTION_MAX;
    input.placeholder = 'For example: which inputs does it need?';
    input.setAttribute('aria-describedby', id + '-note');
    var button = make('button', 'assistant-btn assistant-typed-btn', 'Ask');
    button.type = 'submit';
    form.appendChild(label);
    form.appendChild(input);
    form.appendChild(button);

    var note = make('p', 'assistant-typed-note');
    note.id = id + '-note';
    note.appendChild(document.createTextNode(NOTE));
    var link = make('a', 'assistant-typed-link', 'Privacy Policy');
    link.href = '/privacy.html';
    note.appendChild(link);
    note.appendChild(document.createTextNode(', section 5.'));

    var answer = make('div', 'assistant-answer assistant-typed-answer');
    answer.id = id + '-answer';
    answer.setAttribute('aria-live', 'polite');
    answer.setAttribute('aria-atomic', 'true');
    answer.setAttribute('tabindex', '-1');

    root.appendChild(form);
    root.appendChild(note);
    root.appendChild(answer);
    slot.appendChild(root);

    function say(lines, className) {
      clear(answer);
      lines.forEach(function (line) { answer.appendChild(make('p', className || 'assistant-text', line)); });
    }

    function show(question, reply) {
      clear(answer);
      answer.appendChild(make('p', 'assistant-q', 'You asked: ' + question));
      paragraphs(answer, reply.answer);
      if (reply.functions.length) {
        var line = make('p', 'assistant-source', 'Functions: ');
        reply.functions.forEach(function (fn, index) {
          if (index) line.appendChild(document.createTextNode(', '));
          line.appendChild(make('code', 'assistant-code', fn));
        });
        answer.appendChild(line);
      }
      if (reply.example) {
        answer.appendChild(make('p', 'assistant-q', 'Checked example inputs for ' + reply.example.fn));
        var pre = make('pre', 'assistant-typed-json');
        pre.appendChild(make('code', '', reply.example.text));
        answer.appendChild(pre);
        answer.appendChild(make('p', 'assistant-source',
          'Copy these into the form below; the form is not filled in for you.'));
      }
      answer.appendChild(make('p', 'assistant-source', reply.source === 'live'
        ? 'Written by an AI model (Claude) from the pyvar catalogue and checked against it. It can be wrong.'
        : 'From the pyvar catalogue'));
    }

    function finish(timer) {
      if (timer) clearTimeout(timer);
      busy = false;
      button.disabled = false;
      answer.setAttribute('aria-busy', 'false');
    }

    function ask() {
      if (busy) return;
      var question = input.value.trim();
      if (question === '') { say(['Type a question first.']); return; }
      if (question.length > QUESTION_MAX) {
        say(['That question is too long.', 'Use at most ' + QUESTION_MAX + ' characters.']);
        return;
      }
      busy = true;
      button.disabled = true;
      answer.setAttribute('aria-busy', 'true');
      say(['Asking\u2026'], 'assistant-q');

      var headers = { 'Content-Type': 'application/json', 'Accept': 'application/json' };
      var token = readToken();
      if (token) headers.Authorization = 'Bearer ' + token;
      var controller = typeof AbortController === 'function' ? new AbortController() : null;
      var timer = controller ? setTimeout(function () { controller.abort(); }, TIMEOUT_MS) : null;
      var options = {
        method: 'POST',
        credentials: 'omit',
        headers: headers,
        body: JSON.stringify({ question: question, function: name, history: history.slice(-HISTORY_MAX) })
      };
      if (controller) options.signal = controller.signal;

      fetch(ENDPOINT, options).then(function (res) {
        var retry = res.headers && typeof res.headers.get === 'function' ? parseInt(res.headers.get('Retry-After') || '', 10) : NaN;
        return res.json().then(
          function (data) { return { status: res.status, data: data, retry: retry }; },
          function () { return { status: res.status, data: null, retry: retry }; }
        );
      }).then(function (r) {
        var reply = r.status === 200 ? validate(r.data) : null;
        if (reply) {
          show(question, reply);
          history.push({ q: question, a: reply.answer.slice(0, ANSWER_MAX) });
          if (history.length > HISTORY_MAX) history.shift();
          input.value = '';
        } else {
          say(r.status === 200 ? [GENERIC, HINT] : problem(r.status, r.data, r.retry));
        }
      }).catch(function () {
        say([GENERIC, HINT]);
      }).then(function () {
        finish(timer);
      });
    }

    form.addEventListener('submit', function (event) {
      event.preventDefault();
      ask();
    });
  }

  function mount(name) {
    var slot = document.getElementById('assistantTypedSlot');
    if (!slot || !NAME_OK.test(name || '') || slot.firstChild || slot.dataset.fn !== name) return;
    build(slot, name);
  }

  document.addEventListener('pyvar:tryit-open', function (event) {
    mount(event && event.detail ? event.detail.name : '');
  });

  // A panel that was opened before this script finished loading.
  var open = document.getElementById('assistantTypedSlot');
  if (open) mount(open.dataset.fn);
})();
