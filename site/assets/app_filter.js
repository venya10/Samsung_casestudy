/* Live filter bar + click-to-filter charts, talking to the /api/tables route
   src/serve.py adds (src/site_data.py calls the same insights.py functions the
   static-site build calls, so a filtered number here cannot disagree with the
   unfiltered build).

   Requires `python src/serve.py` running. Without it (double-clicking
   index.html, or the server not started) the filter bar shows disabled with a
   note, and the page keeps showing the full, unfiltered numbers Python baked
   in at build time -- same honest-fallback pattern as the AI chat. */
window.Filters = (function () {
  'use strict';

  var OPTIONS = {
    week: [1, 2, 3, 4, 5, 6, 7, 8],
    channel: ['TV', 'Paid Social', 'Search', 'Influencer', 'B2B Roadshow', 'Retail', 'PR', 'Website'],
    product: ['Galaxy Z Fold8', 'Galaxy Z Flip8', 'Galaxy S24', 'Galaxy Tab S10', 'Galaxy Watch6', 'Galaxy Buds3'],
    market: ['SGE', 'SESAR', 'SEEG', 'SELV', 'SEMAG', 'SEPAK', 'SETK', 'SEIL']
  };
  var MARKET_LABEL = {
    SGE: 'Gulf', SESAR: 'Saudi Arabia', SEEG: 'Egypt', SELV: 'Levant',
    SEMAG: 'Maghreb', SEPAK: 'Pakistan', SETK: 'Türkiye', SEIL: 'Israel'
  };
  var DIM_LABEL = { week: 'Week', channel: 'Channel', product: 'Product', market: 'Market' };
  function fmtVal(dim, v) { return dim === 'market' ? (v + ' (' + MARKET_LABEL[v] + ')') : (dim === 'week' ? 'Wk ' + v : v); }

  var STATE = { week: [], channel: [], product: [], market: [] }; // [] == all
  var live = null;       // null = unknown yet, true/false once checked
  var Pages = {};        // pageId -> function(tables, active)
  var currentPage = null;
  var requestSeq = 0;    // guards against an in-flight fetch resolving after a newer one
  var liveCallbacks = [];

  function esc(s) { return Charts.esc(s); }

  // Fires cb(isLive) once the initial /api/health check resolves -- immediately
  // if it already has. Lets a page-specific control (e.g. the Early Warning
  // sensitivity slider) gate itself the same way the filter bar does, without
  // re-running its own health check or guessing at timing.
  function onLiveKnown(cb) {
    if (live !== null) { cb(live); return; }
    liveCallbacks.push(cb);
  }

  /* ------------------------------------------------------------- network */
  function checkLive() {
    return fetch('/api/health').then(function (r) { return r.ok ? r.json() : { live: false }; })
      .then(function (j) { live = !!j.live; return live; })
      .catch(function () { live = false; return false; });
  }

  function fetchTables() {
    return fetch('/api/tables', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(STATE)
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (j) {
      if (j && j.error) throw new Error(j.error);
      return j;
    });
  }

  /* --------------------------------------------------------------- state */
  function isFiltered(dim) { return dim ? STATE[dim].length > 0 : Object.keys(STATE).some(function (d) { return STATE[d].length; }); }

  function toggleValue(dim, val) {
    var cur = STATE[dim];
    if (cur.length === 0) { STATE[dim] = [val]; return; }               // isolate on first click
    var i = cur.indexOf(val);
    if (i >= 0) { cur.splice(i, 1); }                                    // remove
    else { cur.push(val); }                                             // extend
  }

  function resetAll() { Object.keys(STATE).forEach(function (d) { STATE[d] = []; }); }

  /* ------------------------------------------------------------ menu ui */
  function closeAllMenus() {
    document.querySelectorAll('.fmenu.open').forEach(function (m) { m.classList.remove('open'); });
  }
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.fset')) closeAllMenus();
  });

  function buildMenuHtml(dim) {
    var opts = OPTIONS[dim];
    var boxes = opts.map(function (v) {
      var checked = STATE[dim].length === 0 || STATE[dim].indexOf(v) >= 0;
      return '<label><input type="checkbox" data-dim="' + dim + '" value="' + esc(v) + '"' +
        (checked ? ' checked' : '') + '>' + esc(fmtVal(dim, v)) + '</label>';
    }).join('');
    return '<div class="fmenu" data-menu="' + dim + '">' +
      '<div class="fmenu-head"><button type="button" data-act="all" data-dim="' + dim + '">Select all</button>' +
      '<button type="button" data-act="clear" data-dim="' + dim + '">Clear</button></div>' + boxes + '</div>';
  }

  function pillLabel(dim) {
    var n = STATE[dim].length, total = OPTIONS[dim].length;
    var summary = n === 0 ? 'All' : (n === total ? 'All' : n + ' selected');
    return '<span>' + DIM_LABEL[dim] + '</span> <span class="n">' + summary + '</span>';
  }

  function buildFilterBar(mount, pageId) {
    var dims = Object.keys(OPTIONS);
    mount.innerHTML =
      '<div class="fbar" id="fbar-' + pageId + '">' +
      dims.map(function (d) {
        return '<div class="fset"><button type="button" class="fbtn" data-dim="' + d + '">' + pillLabel(d) +
          '<svg viewBox="0 0 10 6" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M1 1l4 4 4-4"/></svg></button>' +
          buildMenuHtml(d) + '</div>';
      }).join('') +
      '<button type="button" class="fbar-reset">Reset</button>' +
      '<span class="fbar-note" id="fbar-note-' + pageId + '"></span>' +
      '</div>';

    mount.querySelectorAll('.fbtn').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var dim = btn.getAttribute('data-dim');
        var menu = mount.querySelector('.fmenu[data-menu="' + dim + '"]');
        var wasOpen = menu.classList.contains('open');
        closeAllMenus();
        if (!wasOpen) menu.classList.add('open');
      });
    });
    mount.querySelectorAll('.fmenu input[type=checkbox]').forEach(function (cb) {
      cb.addEventListener('change', function () {
        var dim = cb.getAttribute('data-dim'), v = cb.value;
        var vNorm = dim === 'week' ? parseInt(v, 10) : v;
        // Expand "all" ([]) to an explicit list to mutate, then collapse back to []
        // if the edit ends up selecting everything OR nothing -- matches
        // app/state.py's filter_bar_controls exactly: an empty selection clears
        // the filter (shows everything) rather than matching zero rows, since [] is
        // this app's (and the API's) actual "no filter on this dimension" value.
        var cur = STATE[dim].length ? STATE[dim].slice() : OPTIONS[dim].slice();
        var i = cur.indexOf(vNorm);
        if (cb.checked) { if (i < 0) cur.push(vNorm); }
        else if (i >= 0) { cur.splice(i, 1); }
        STATE[dim] = (cur.length === 0 || cur.length === OPTIONS[dim].length) ? [] : cur;
        refresh(pageId, mount);
      });
    });
    mount.querySelectorAll('.fmenu-head button').forEach(function (b) {
      b.addEventListener('click', function () {
        // "Select all" and "Clear" both converge on [] ("no filter") -- see the
        // checkbox handler above for why an empty selection can't mean anything else.
        STATE[b.getAttribute('data-dim')] = [];
        refresh(pageId, mount);
      });
    });
    mount.querySelector('.fbar-reset').addEventListener('click', function () {
      resetAll();
      refresh(pageId, mount);
    });

    setLiveUi(mount, pageId);
  }

  function setLiveUi(mount, pageId) {
    var bar = mount.querySelector('.fbar');
    if (live === false) {
      bar.querySelectorAll('.fbtn').forEach(function (b) { b.disabled = true; b.title = 'Run python src/serve.py for interactive filtering'; });
      var note = mount.querySelector('#fbar-note-' + pageId);
      if (note) note.innerHTML = '<span class="fbar-offline">Offline — showing the full dataset. Run <code>python src/serve.py</code> to filter live.</span>';
    }
  }

  function noteEl(pageId) { return document.getElementById('fbar-note-' + pageId); }

  function showEmptyState(pageId) {
    // Mirrors app/views/*.py's own "No rows match the current filters." stop --
    // same wording, same rule: don't guess at a filtered view with nothing in it,
    // say so and leave the last real render on screen rather than going stale
    // silently.
    var note = noteEl(pageId);
    if (note) { note.className = 'fbar-note fbar-error'; note.textContent = 'No rows match the current filters.'; }
  }

  function showFetchError(pageId) {
    var note = noteEl(pageId);
    if (note) { note.className = 'fbar-note fbar-error'; note.textContent = "Couldn't reach the live server — showing the last successful view."; }
  }

  function refresh(pageId, mount) {
    if (live === false) return;
    var seq = ++requestSeq;
    // buildFilterBar() below fully rebuilds the menu markup, which would
    // otherwise silently drop whichever dropdown the user has open --
    // closing it after every single checkbox click and making it
    // impossible to check/uncheck more than one option per open. Remember
    // it here and re-open the same dimension's menu once rebuilt.
    var openMenu = mount.querySelector('.fmenu.open');
    var openDim = openMenu ? openMenu.getAttribute('data-menu') : null;
    fetchTables().then(function (t) {
      if (seq !== requestSeq) return; // a newer filter change already superseded this response
      buildFilterBar(mount, pageId); // rebuild pills/menus from current STATE, re-bind handlers
      if (openDim) {
        var reopened = mount.querySelector('.fmenu[data-menu="' + openDim + '"]');
        if (reopened) reopened.classList.add('open');
      }
      if (t.fact_base && t.fact_base.length === 0) {
        showEmptyState(pageId);
        return; // leave the page's last real render in place rather than blanking it
      }
      var note = noteEl(pageId);
      if (note) note.textContent = '';
      if (Pages[pageId]) Pages[pageId](t, STATE);
    }).catch(function () {
      if (seq !== requestSeq) return;
      showFetchError(pageId);
    });
  }

  /* ---------------------------------------------------- click-to-filter */
  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-fdim]');
    if (!el || live === false || live === null) return;
    var dim = el.getAttribute('data-fdim'), raw = el.getAttribute('data-fval');
    var val = dim === 'week' ? parseInt(raw, 10) : raw;
    toggleValue(dim, val);
    var mount = document.getElementById('mount-filterbar');
    if (mount && currentPage) refresh(currentPage, mount);
  });

  /* ------------------------------------------------------------- boot */
  function boot() {
    var mount = document.getElementById('mount-filterbar');
    if (!mount) return;
    var pageId = mount.getAttribute('data-page');
    currentPage = pageId;
    buildFilterBar(mount, pageId);
    checkLive().then(function (isLive) {
      setLiveUi(mount, pageId);
      liveCallbacks.forEach(function (cb) { cb(isLive); });
      liveCallbacks = [];
    });
  }

  document.addEventListener('DOMContentLoaded', boot);

  return {
    OPTIONS: OPTIONS, MARKET_LABEL: MARKET_LABEL, STATE: STATE, Pages: Pages,
    refresh: refresh, onLiveKnown: onLiveKnown, isLive: function () { return live; }
  };
})();
