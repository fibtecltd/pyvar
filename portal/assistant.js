// pyvar portal assistant: the "About this function" buttons in a function's Try-it panel.
//
// What it is: three fixed questions (What it does / When to use it / Compare with...) answered from a bank of
// answers written ahead of time and checked (assistant/bank.py). It is a reader. It sends nothing to the server:
// no request body, no cookie, no query string, nothing typed by the visitor. The only requests it makes are two
// GETs of static files (below).
//
// Loading: pyvar.js adds this script only when GET /public/config says assistant_enabled is true, and passes the
// bank version in data-bank-version. pyvar.js then fires a `pyvar:tryit-open` event each time it opens a Try-it
// panel and leaves an empty <div id="assistantSlot" data-fn="<function name>"> in it; this file fills that slot.
//
// First use is the first time a function's Try-it panel is opened: GET /assistant/bank/<version>/<function>.json
// (about 3 KB, never all 385 files). Quiet failure: if that request fails, answers anything but 200 (a 404 for a
// missing or stale bank version, say), is not JSON of the expected shape or holds no answer, the slot stays empty
// and nothing is shown, so a missing or stale bank can never leave buttons that lead nowhere.
//
// Safety: every string from the bank is put in the page with textContent / createTextNode, never as HTML. This
// file must not use innerHTML, eval, document.write or inline event handlers (tests/test_assistant_widget.py
// scans for them).
(function () {
  'use strict';

  var script = document.currentScript;
  var VERSION = script && script.dataset ? script.dataset.bankVersion || '' : '';
  if (!/^[A-Za-z0-9._-]+$/.test(VERSION)) return;
  var BASE = '/assistant/bank/' + encodeURIComponent(VERSION) + '/';
  var SOURCE_LABEL = 'From the pyvar catalogue';
  var NAME_OK = /^[A-Za-z0-9_]+$/;

  var banks = {};   // function name -> Promise of the validated bank file, or null
  var counter = 0;  // unique ids for aria-labelledby / for

  function make(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function isEntry(value) {
    return !!value && typeof value === 'object' && typeof value.text === 'string' && value.text.trim() !== '';
  }

  // The part of a bank file the widget uses, or null if the file is not what a build writes.
  function validate(data) {
    if (!data || typeof data !== 'object' || Array.isArray(data)) return null;
    var clean = { explain: null, when: null, compare: {} };
    if (isEntry(data.explain)) clean.explain = data.explain.text;
    if (isEntry(data.when)) clean.when = data.when.text;
    if (data.compare && typeof data.compare === 'object' && !Array.isArray(data.compare)) {
      Object.keys(data.compare).sort().forEach(function (name) {
        if (NAME_OK.test(name) && isEntry(data.compare[name])) clean.compare[name] = data.compare[name].text;
      });
    }
    if (!clean.explain && !clean.when && Object.keys(clean.compare).length === 0) return null;
    return clean;
  }

  function loadBank(name) {
    if (!banks[name]) {
      banks[name] = fetch(BASE + encodeURIComponent(name) + '.json', { credentials: 'omit' })
        .then(function (res) { return res.ok ? res.json() : null; })
        .then(validate)
        .catch(function () { return null; });
    }
    return banks[name];
  }

  // `code` spans (backticks) become <code> and **bold** becomes <strong>; everything else is plain text.
  // A ** without its partner stays as it was written.
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
  function render(target, text, label) {
    while (target.firstChild) target.removeChild(target.firstChild);
    target.appendChild(make('p', 'assistant-q', label));
    var list = null;
    text.split('\n').forEach(function (raw) {
      var line = raw.trim();
      if (line === '') { list = null; return; }
      var bullet = /^[-*•]\s+(.*)$/.exec(line);
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
    target.appendChild(make('p', 'assistant-source', SOURCE_LABEL));
  }

  function build(slot, bank) {
    counter += 1;
    var id = 'assistant-' + counter;
    var root = make('section', 'assistant');
    root.setAttribute('aria-labelledby', id + '-title');
    root.appendChild(make('h3', 'assistant-title', 'About this function')).id = id + '-title';

    var controls = make('div', 'assistant-controls');
    controls.setAttribute('role', 'group');
    controls.setAttribute('aria-labelledby', id + '-title');
    var answer = make('div', 'assistant-answer');
    answer.id = id + '-answer';
    answer.setAttribute('aria-live', 'polite');
    answer.setAttribute('aria-atomic', 'true');
    answer.setAttribute('tabindex', '-1');

    var buttons = [];
    function press(active) {
      buttons.forEach(function (b) { b.setAttribute('aria-pressed', b === active ? 'true' : 'false'); });
    }
    function addButton(label, text) {
      var button = make('button', 'assistant-btn', label);
      button.type = 'button';
      button.setAttribute('aria-pressed', 'false');
      button.setAttribute('aria-controls', answer.id);
      button.addEventListener('click', function () {
        press(button);
        select.value = '';
        render(answer, text, label);
      });
      controls.appendChild(button);
      buttons.push(button);
    }
    var select = make('select', 'assistant-select');
    if (bank.explain) addButton('What it does', bank.explain);
    if (bank.when) addButton('When to use it', bank.when);

    var siblings = Object.keys(bank.compare);
    if (siblings.length) {
      var wrap = make('span', 'assistant-compare');
      var label = make('label', 'assistant-sr', 'Compare with another function');
      label.htmlFor = id + '-compare';
      select.id = id + '-compare';
      select.setAttribute('aria-controls', answer.id);
      var first = make('option', null, 'Compare with…');
      first.value = '';
      select.appendChild(first);
      siblings.forEach(function (name) {
        var option = make('option', null, name);
        option.value = name;
        select.appendChild(option);
      });
      select.addEventListener('change', function () {
        var name = select.value;
        press(null);
        if (name && bank.compare[name]) render(answer, bank.compare[name], 'Compared with ' + name);
      });
      wrap.appendChild(label);
      wrap.appendChild(select);
      controls.appendChild(wrap);
    }
    root.appendChild(controls);
    root.appendChild(answer);
    slot.appendChild(root);
  }

  function mount(name) {
    var slot = document.getElementById('assistantSlot');
    if (!slot || !NAME_OK.test(name || '') || slot.firstChild) return;
    loadBank(name).then(function (bank) {
      // The panel may have been closed, or opened for another function, while the file was loading.
      if (!bank || !slot.isConnected || slot.dataset.fn !== name || slot.firstChild) return;
      build(slot, bank);
    });
  }

  document.addEventListener('pyvar:tryit-open', function (event) {
    mount(event && event.detail ? event.detail.name : '');
  });

  // A panel that was opened before this script finished loading.
  var open = document.getElementById('assistantSlot');
  if (open) mount(open.dataset.fn);
})();
