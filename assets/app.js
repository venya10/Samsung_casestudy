/* Shared chart tooltip + crosshair, and the assistant chat client.
   Vanilla — no framework, no build step, no CDN. The site opens offline. */

(function () {
  'use strict';

  /* ------------------------------------------------------------ sidebar */
  var sbToggle = document.getElementById('sbToggle');
  if (sbToggle) {
    sbToggle.addEventListener('click', function () {
      var collapsed = document.documentElement.classList.toggle('sb-collapsed');
      try { localStorage.setItem('sb-collapsed', collapsed ? '1' : '0'); } catch (e) {}
      sbToggle.title = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
    });
  }

  /* ------------------------------------------------------------- tooltip */
  var tip = document.createElement('div');
  tip.id = 'tip';
  document.body.appendChild(tip);

  function showTip(evt, title, body) {
    tip.innerHTML = '<div class="tt">' + title + '</div>' +
                    (body ? '<div class="tb">' + body + '</div>' : '');
    tip.style.opacity = '1';
    moveTip(evt);
  }

  function moveTip(evt) {
    var pad = 14;
    var r = tip.getBoundingClientRect();
    var x = evt.clientX + pad;
    var y = evt.clientY + pad;
    if (x + r.width > window.innerWidth - 8) x = evt.clientX - r.width - pad;
    if (y + r.height > window.innerHeight - 8) y = evt.clientY - r.height - pad;
    tip.style.left = x + 'px';
    tip.style.top = y + 'px';
  }

  function hideTip() { tip.style.opacity = '0'; }

  // Per-mark hover: bars, scatter points.
  document.addEventListener('mouseover', function (e) {
    var el = e.target.closest('[data-title]');
    if (!el) return;
    showTip(e, el.getAttribute('data-title'), el.getAttribute('data-body') || '');
  });
  document.addEventListener('mousemove', function (e) {
    if (tip.style.opacity === '1') moveTip(e);
  });
  document.addEventListener('mouseout', function (e) {
    if (e.target.closest('[data-title]')) hideTip();
  });

  // Line charts: crosshair follows the hovered x-band.
  document.querySelectorAll('svg.chart .hit rect').forEach(function (band) {
    band.addEventListener('mouseenter', function () {
      var svg = band.closest('svg');
      var cross = svg.querySelector('.crosshair');
      if (!cross) return;
      var x = band.getAttribute('data-x');
      cross.setAttribute('x1', x);
      cross.setAttribute('x2', x);
      cross.setAttribute('opacity', '1');
    });
  });
  document.querySelectorAll('svg.chart').forEach(function (svg) {
    svg.addEventListener('mouseleave', function () {
      var cross = svg.querySelector('.crosshair');
      if (cross) cross.setAttribute('opacity', '0');
      hideTip();
    });
  });

  /* ------------------------------------------------------ table explorer */
  // Data is embedded in the page rather than fetched, so the explorer works when
  // the site is opened straight from disk — fetch() against file:// is blocked.
  var explorer = document.getElementById('explorer');
  if (explorer && window.__TABLES__) {
    var TABLES = window.__TABLES__;
    var state = { name: Object.keys(TABLES)[0], q: '', sort: null, asc: true, limit: 50 };

    var tabsEl = document.getElementById('tbl-tabs');
    var search = document.getElementById('tbl-search');
    var meta = document.getElementById('tbl-meta');
    var host = document.getElementById('tbl-host');
    var more = document.getElementById('tbl-more');
    var dl = document.getElementById('tbl-download');

    var tabButtons = {};
    Object.keys(TABLES).forEach(function (name) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'tab' + (name === state.name ? ' active' : '');
      b.textContent = TABLES[name].label || name;
      b.setAttribute('role', 'tab');
      b.addEventListener('click', function () {
        if (state.name === name) return;
        state.name = name; state.sort = null; state.limit = 50; state.q = '';
        if (search) search.value = '';
        Object.keys(tabButtons).forEach(function (n) {
          tabButtons[n].classList.toggle('active', n === name);
        });
        render();
      });
      tabsEl.appendChild(b);
      tabButtons[name] = b;
    });

    function fmt(v) {
      if (v === null || v === undefined || v === '') return '<span class="tbl-null">—</span>';
      if (typeof v === 'number') {
        // Comma-separated, capped at 2 decimal places everywhere -- integers
        // (row counts, weeks) show with none, matching toLocaleString's default.
        if (Number.isInteger(v)) return v.toLocaleString();
        return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      }
      return String(v).replace(/</g, '&lt;');
    }

    function render() {
      var t = TABLES[state.name];
      var cols = t.cols;
      var rows = t.rows;

      if (state.q) {
        var q = state.q.toLowerCase();
        rows = rows.filter(function (r) {
          return r.some(function (v) {
            return v !== null && String(v).toLowerCase().indexOf(q) >= 0;
          });
        });
      }
      if (state.sort !== null) {
        var i = state.sort, dir = state.asc ? 1 : -1;
        rows = rows.slice().sort(function (a, b) {
          var x = a[i], y = b[i];
          if (x === null) return 1;
          if (y === null) return -1;
          if (typeof x === 'number' && typeof y === 'number') return (x - y) * dir;
          return String(x).localeCompare(String(y)) * dir;
        });
      }

      var shown = rows.slice(0, state.limit);
      var derived = t.derived || [];
      var head = cols.map(function (c, i) {
        var arrow = state.sort === i ? (state.asc ? ' ▲' : ' ▼') : '';
        var cls = 'tbl-h' + (derived.indexOf(c) >= 0 ? ' derived' : '');
        return '<th class="' + cls + '" data-i="' + i + '">' + c.replace(/_/g, ' ') + arrow + '</th>';
      }).join('');
      var body = shown.map(function (r) {
        return '<tr>' + r.map(function (v) {
          var cls = typeof v === 'number' ? ' class="num"' : '';
          return '<td' + cls + '>' + fmt(v) + '</td>';
        }).join('') + '</tr>';
      }).join('');

      host.innerHTML = '<table><thead><tr>' + head + '</tr></thead><tbody>' + body + '</tbody></table>';
      meta.textContent = rows.length.toLocaleString() + ' of ' +
        t.rows.length.toLocaleString() + ' rows · ' + cols.length + ' columns' +
        (t.note ? ' · ' + t.note : '');

      // Point the download at the table currently on screen. The file is always
      // the full table -- filtering and the row cap are display-only, and handing
      // someone a silently truncated export would be worse than no export.
      // The href is the real file (named by the internal table); the suggested
      // filename is the business name shown on the tab.
      if (dl) {
        var label = t.label || state.name;
        dl.setAttribute('href', 'data/' + state.name + '.csv');
        dl.setAttribute('download', label + '.csv');
        dl.title = 'Download ' + label + '.csv — all ' +
          t.rows.length.toLocaleString() + ' rows';
      }
      more.style.display = rows.length > state.limit ? 'inline-block' : 'none';
      more.textContent = 'Show ' + Math.min(200, rows.length - state.limit) + ' more';

      host.querySelectorAll('.tbl-h').forEach(function (th) {
        th.addEventListener('click', function () {
          var i = +th.getAttribute('data-i');
          state.asc = state.sort === i ? !state.asc : true;
          state.sort = i;
          render();
        });
      });
    }

    search.addEventListener('input', function () {
      state.q = search.value; state.limit = 50; render();
    });
    more.addEventListener('click', function () { state.limit += 200; render(); });
    render();
  }

  /* ------------------------------------------------------- sortable table */
  // Any table rendered by table(..., sortable=True) (Python) or
  // C.table(rows, cols, null, {sortable:true}) (JS): click a header to sort
  // ascending, click again for descending. Sorts by each cell's data-sort
  // attribute (the raw value) rather than its formatted text, so "24,908"
  // and "1.28x" compare correctly instead of as strings. Exposed on window
  // so app_pages.js can re-wire a table's headers after replacing its
  // innerHTML on a live filter change.
  function enhanceSortableTables(root) {
    (root || document).querySelectorAll('.sortable-table').forEach(function (wrap) {
      var tbl = wrap.querySelector('table');
      var tbody = tbl && tbl.querySelector('tbody');
      if (!tbl || !tbody) return;
      var state = { i: null, asc: true };
      tbl.querySelectorAll('th.sort-h').forEach(function (th) {
        th.addEventListener('click', function () {
          var i = +th.getAttribute('data-i');
          state.asc = state.i === i ? !state.asc : true;
          state.i = i;
          tbl.querySelectorAll('th.sort-h').forEach(function (h) {
            h.textContent = h.textContent.replace(/ [▲▼]$/, '');
          });
          th.textContent += state.asc ? ' ▲' : ' ▼';
          var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
          rows.sort(function (ra, rb) {
            var va = ra.children[i].getAttribute('data-sort') || '';
            var vb = rb.children[i].getAttribute('data-sort') || '';
            if (va === '' && vb === '') return 0;
            if (va === '') return 1;
            if (vb === '') return -1;
            var na = Number(va), nb = Number(vb);
            var c = (va.trim() !== '' && vb.trim() !== '' && !isNaN(na) && !isNaN(nb))
              ? na - nb : va.localeCompare(vb);
            return state.asc ? c : -c;
          });
          rows.forEach(function (row) { tbody.appendChild(row); });
        });
      });
    });
  }
  window.enhanceSortableTables = enhanceSortableTables;
  enhanceSortableTables(document);

  /* --------------------------------------------------------------- chat */
  var log = document.getElementById('chat-log');
  if (!log) return;

  var input = document.getElementById('chat-input');
  var send = document.getElementById('chat-send');
  var canned = window.__CANNED__ || {};
  var live = false;

  // Is the local API up? If not, fall back to the prepared answers baked into
  // the page, and say so rather than pretending.
  fetch('/api/health')
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) {
      live = !!(j && j.live);
      var el = document.getElementById('chat-status');
      if (!el) return;
      el.innerHTML = live
        ? '<span class="status-dot" style="background:var(--good)"></span>Live — Gemini is answering with SQL against the database'
        : '<span class="status-dot" style="background:var(--warning)"></span>Offline — showing prepared answers. Run <code>python src/serve.py</code> with a GEMINI_API_KEY for live answers.';
    })
    .catch(function () {
      var el = document.getElementById('chat-status');
      if (el) el.innerHTML = '<span class="status-dot" style="background:var(--warning)"></span>Offline — showing prepared answers. Run <code>python src/serve.py</code> with a GEMINI_API_KEY for live answers.';
    });

  function bubble(role, htmlContent) {
    var d = document.createElement('div');
    d.className = 'msg ' + role;
    d.innerHTML = '<div class="msg-role">' + (role === 'user' ? 'You' : 'Marketing Intelligence') +
                  '</div><div class="bubble">' + htmlContent + '</div>';
    log.appendChild(d);
    d.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    return d;
  }

  function normalise(s) {
    return s.toLowerCase().replace(/[^a-z ]/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function bestCanned(q) {
    var n = normalise(q);
    var best = null, bestScore = 0;
    Object.keys(canned).forEach(function (key) {
      var words = normalise(key).split(' ');
      var hits = 0;
      words.forEach(function (w) { if (w.length > 3 && n.indexOf(w) >= 0) hits++; });
      var score = hits / Math.max(words.length, 1);
      if (score > bestScore) { bestScore = score; best = key; }
    });
    return bestScore >= 0.25 ? canned[best] : null;
  }

  function ask(q) {
    if (!q.trim()) return;
    bubble('user', q.replace(/</g, '&lt;'));
    input.value = '';
    send.disabled = true;
    var pending = bubble('bot', '<span style="color:var(--muted)">Querying the marketing database…</span>');

    var done = function (htmlContent) {
      pending.querySelector('.bubble').innerHTML = htmlContent;
      send.disabled = false;
      input.focus();
    };

    if (!live) {
      setTimeout(function () {
        var hit = bestCanned(q);
        done(hit || '<p>Without the live assistant running I can only answer the prepared questions above. Start it with <code>python src/serve.py</code> after setting <code>GEMINI_API_KEY</code>.</p>');
      }, 220);
      return;
    }

    fetch('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q })
    })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var out = j.answer_html || '<p>No answer returned.</p>';
        if (j.tool_calls && j.tool_calls.length) {
          out += '<details class="sql-view"><summary>How this was answered — ' +
                 j.tool_calls.length + ' tool call' + (j.tool_calls.length > 1 ? 's' : '') +
                 '</summary>';
          j.tool_calls.forEach(function (c, i) {
            out += '<div style="margin-top:9px"><b>' + (i + 1) + '. ' + c.tool + '</b>';
            if (c.sql) out += '<pre>' + c.sql.replace(/</g, '&lt;') + '</pre>';
            out += '</div>';
          });
          out += '</details>';
        }
        done(out);
      })
      .catch(function (err) {
        done('<p style="color:var(--critical)">Request failed: ' +
             String(err).replace(/</g, '&lt;') + '</p>');
      });
  }

  send.addEventListener('click', function () { ask(input.value); });
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') ask(input.value);
  });
  document.querySelectorAll('.chip').forEach(function (chip) {
    chip.addEventListener('click', function () { ask(chip.textContent); });
  });
})();
