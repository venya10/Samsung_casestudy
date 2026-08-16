/* Inline-SVG chart primitives -- JS port of src/site_charts.py, kept
   geometrically identical (same padding, same tick algorithm, same label
   placement rules) so a chart looks the same whether the page rendered it at
   build time or the browser re-rendered it after a filter change.

   Marks that can drive the filter bar carry data-fdim/data-fval, picked up by
   app_filter.js's single delegated click handler -- the same pattern the
   tooltip already uses for data-title/data-body in app.js. */
window.Charts = (function () {
  'use strict';

  /* Palette ported from the visual reference's design system -- see the
     matching comment in src/site_charts.py for what's 1:1 and what (the
     8-way SERIES set) has no reference equivalent and is kept as-is. */
  var SERIES = ['#2B6DEF', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'];
  var SERIES_MUTED = '#C7D6FB';
  // Same 6-hue pastel cycle as the KPI card icon accents (app.css's
  // .kpis .kpi:nth-child(6n+N)) -- see the matching comment in
  // src/site_charts.py for why this is reused rather than a new palette.
  var SERIES_PASTEL = ['#7FA8FF', '#6FCFA0', '#F2AD5C', '#B39BF0', '#F291B7', '#62C4C2', '#F2D98A', '#F2A6A6'];
  var STATUS = { good: '#0B7A54', warning: '#B26A00', serious: '#ec835a', critical: '#C0272D' };
  var INK = '#0A1020', INK_2 = '#333E52', MUTED = '#707C91', FAINT = '#9AA5B7', GRID = '#EFF2F7', BASELINE = '#E4E8EF';

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fAttrs(dim, val) {
    return (dim && val !== undefined && val !== null) ? ' data-fdim="' + esc(dim) + '" data-fval="' + esc(val) + '"' : '';
  }

  /* --------------------------------------------------------------- misc */
  function _fval(opts, i, lab) {
    return opts.filterVals ? opts.filterVals[i] : lab;
  }

  /* -------------------------------------------------------------- format */
  function aed(v, dp) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    dp = dp || 0;
    var a = Math.abs(v), sign = v < 0 ? '-' : '';
    if (a >= 1e9) return sign + (a / 1e9).toFixed(2) + 'bn AED';
    if (a >= 1e6) return sign + (a / 1e6).toFixed(1) + 'm AED';
    if (a >= 1e3) return sign + Math.round(a / 1e3).toLocaleString() + 'k AED';
    return sign + a.toFixed(dp) + ' AED';
  }
  function aedShort(v) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    var a = Math.abs(v), sign = v < 0 ? '-' : '';
    if (a >= 1e6) return sign + (a / 1e6).toFixed(1) + 'm';
    if (a >= 1e3) return sign + Math.round(a / 1e3).toLocaleString() + 'k';
    return sign + Math.round(a).toLocaleString();
  }
  function xFmt(v) { return (v === null || v === undefined || isNaN(v)) ? '—' : v.toFixed(2) + 'x'; }
  function pct(v, dp) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    return (v * 100).toFixed(dp === undefined ? 0 : dp) + '%';
  }
  function num(v, dp) {
    if (v === null || v === undefined || isNaN(v)) return '—';
    return v.toLocaleString(undefined, { minimumFractionDigits: dp || 0, maximumFractionDigits: dp || 0 });
  }

  /* --------------------------------------------------------------- scale */
  function niceTicks(lo, hi, target) {
    target = target || 5;
    if (hi <= lo) hi = lo + 1;
    var raw = (hi - lo) / Math.max(target, 1);
    var mag = raw > 0 ? Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)) : 1;
    var step = mag;
    [1, 2, 2.5, 5, 10].some(function (mult) { step = mag * mult; return raw <= step; });
    var start = Math.floor(lo / step) * step;
    var ticks = [], v = start;
    while (v <= hi + step * 0.5) { ticks.push(Math.round(v * 1e10) / 1e10); v += step; }
    return ticks;
  }

  /* --------------------------------------------------------- legend/misc */
  function legend(items, opts) {
    // items: [label, color] or [label, color, filterVal]. opts.filterDim makes
    // each chip a click-to-filter target too (a legend label can differ from
    // the raw filter value, same reasoning as barChartH's filterVals).
    // opts.symbol: 'dot' for a square swatch (categorical charts), default a
    // line swatch (series charts) -- matches site_charts.py's legend().
    opts = opts || {};
    var swatchCls = opts.symbol === 'dot' ? 'lg-dot' : 'lg-line';
    return '<div class="legend">' + items.map(function (it) {
      var label = it[0], color = it[1], fval = it.length > 2 ? it[2] : label;
      var fattrs = opts.filterDim ? fAttrs(opts.filterDim, fval) : '';
      return '<span class="lg-item"' + fattrs + '><span class="' + swatchCls + '" style="background:' + color + '"></span>' + esc(label) + '</span>';
    }).join('') + '</div>';
  }

  /* ---------------------------------------------------------- bar chart */
  function barChartH(labels, values, opts) {
    opts = opts || {};
    var n = labels.length, row = opts.rowHeight || 34;
    var padL = 152, padR = 74, padT = 8, padB = 22;
    var width = opts.width || 760;
    var height = opts.height || (padT + padB + row * n);
    var pw = width - padL - padR;
    var colors = opts.colors || labels.map(function () { return SERIES[0]; });
    var vFmt = opts.vFmt || num;
    var labelFmt = opts.labelFmt || vFmt;
    var zeroLine = opts.zeroLine;
    var lo = Math.min(0, Math.min.apply(null, values));
    var hi = Math.max.apply(null, values);
    if (hi === lo) hi = lo + 1;
    var pad = (hi - lo) * 0.02; lo -= pad; hi += pad;
    function X(v) { return padL + (v - lo) / (hi - lo) * pw; }
    var out = ['<svg class="chart" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="xMidYMid meet" data-chart="' + esc(opts.chartId || 'b') + '" role="img">'];
    var xZero = X(zeroLine !== undefined && zeroLine !== null ? zeroLine : 0);

    for (var i = 0; i < n; i++) {
      var lab = labels[i], v = values[i], c = colors[i];
      var y = padT + i * row + 6, h = row - 14;
      var x1 = Math.min(X(v), xZero), x2 = Math.max(X(v), xZero);
      var bw = Math.max(x2 - x1, 1.5);
      // Full-width track behind the bar, ported from the reference's hbars().
      out.push('<rect x="' + padL.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + pw.toFixed(1) + '" height="' + h + '" rx="3" fill="' + GRID + '"/>');
      out.push('<rect x="' + x1.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' + h +
        '" rx="3" fill="' + c + '" data-title="' + esc(lab) + '" data-body="' + esc(labelFmt(v)) + '" class="bar"' +
        fAttrs(opts.filterDim, _fval(opts, i, lab)) + '/>');
      var sub = opts.subs ? opts.subs[i] : null;
      var catY = sub ? (padT + i * row + 16) : (y + h / 2 + 4);
      out.push('<text x="' + (padL - 12) + '" y="' + catY.toFixed(1) + '" text-anchor="end" class="cat">' + esc(lab) + '</text>');
      if (sub) {
        out.push('<text x="' + (padL - 12) + '" y="' + (padT + i * row + 28).toFixed(1) + '" text-anchor="end" class="cat-sub">' + esc(sub) + '</text>');
      }

      var text = labelFmt(v), wEst = text.length * 6.7;
      var positive = v >= (zeroLine || 0);
      var tx, anchor, fill;
      if (positive) {
        if (x2 + 10 + wEst > width - 4) { tx = x2 - 8; anchor = 'end'; fill = '#ffffff'; }
        else { tx = x2 + 8; anchor = 'start'; fill = INK_2; }
      } else {
        if (x1 - 10 - wEst < padL) { tx = x1 + 8; anchor = 'start'; fill = '#ffffff'; }
        else { tx = x1 - 8; anchor = 'end'; fill = INK_2; }
      }
      out.push('<text x="' + tx.toFixed(1) + '" y="' + (y + h / 2 + 4).toFixed(1) + '" text-anchor="' + anchor +
        '" class="val" fill="' + fill + '">' + esc(text) + '</text>');
    }
    if (zeroLine !== undefined || lo < 0) {
      out.push('<line x1="' + xZero.toFixed(1) + '" y1="' + padT + '" x2="' + xZero.toFixed(1) + '" y2="' + (height - padB).toFixed(1) +
        '" stroke="' + BASELINE + '" stroke-width="1"/>');
    }
    out.push('</svg>');
    return out.join('');
  }

  /* --------------------------------------------------------- pie chart */
  // Mirrors site_charts.py's pie_chart() -- see its docstring for why this
  // is its own primitive (a proportion, not a ranked measure) and why its
  // click attribute is data-select-dim/data-select-val rather than the
  // [data-fdim] the page-wide cross-filter listens for.
  function pieChart(labels, values, opts) {
    opts = opts || {};
    var n = labels.length;
    var colors = opts.colors || labels.map(function (_, i) { return SERIES_PASTEL[i % SERIES_PASTEL.length]; });
    var vFmt = opts.vFmt || num;
    var subs = opts.subs;
    var selectDim = opts.selectDim;
    var selected = opts.selected;
    var size = opts.size || 300;
    var total = values.reduce(function (a, b) { return a + b; }, 0) || 1;
    var cx = size / 2, cy = size / 2, r = size / 2 - 6;

    var svg = ['<svg class="chart chart-pie" viewBox="0 0 ' + size + ' ' + size + '" preserveAspectRatio="xMidYMid meet" data-chart="' + esc(opts.chartId || 'pie') + '" role="img">'];
    var legendItems = [];
    var angle = -90;
    for (var i = 0; i < n; i++) {
      var lab = labels[i], v = values[i], c = colors[i];
      var frac = v / total, sweep = frac * 360;
      var a0 = angle * Math.PI / 180, a1 = (angle + sweep) * Math.PI / 180;
      var x1 = cx + r * Math.cos(a0), y1 = cy + r * Math.sin(a0);
      var x2 = cx + r * Math.cos(a1), y2 = cy + r * Math.sin(a1);
      var large = sweep > 180 ? 1 : 0;
      var selCls = (selected != null && lab === selected) ? ' selected' : '';
      var selAttrs = selectDim ? ' data-select-dim="' + esc(selectDim) + '" data-select-val="' + esc(lab) + '"' : '';
      var sub = subs ? ' · ' + esc(subs[i]) : '';
      svg.push('<path class="pie-slice' + selCls + '" d="M' + cx.toFixed(2) + ',' + cy.toFixed(2) +
        ' L' + x1.toFixed(2) + ',' + y1.toFixed(2) + ' A' + r.toFixed(1) + ',' + r.toFixed(1) + ' 0 ' + large + ',1 ' +
        x2.toFixed(2) + ',' + y2.toFixed(2) + ' Z" fill="' + c + '" data-title="' + esc(lab) +
        '" data-body="' + esc(vFmt(v)) + ' · ' + (frac * 100).toFixed(1) + '% of total' + sub + '"' + selAttrs + '/>');
      legendItems.push('<button type="button" class="pie-legend-item' + selCls + '"' + selAttrs + '>' +
        '<span class="lg-dot" style="background:' + c + '"></span>' +
        '<span class="pli-label">' + esc(lab) + '</span>' +
        '<span class="pli-share">' + (frac * 100).toFixed(0) + '%</span></button>');
      angle += sweep;
    }
    svg.push('</svg>');
    return '<div class="pie-block"><div class="pie-svg-wrap">' + svg.join('') + '</div>' +
      '<div class="pie-legend">' + legendItems.join('') + '</div></div>';
  }

  /* ------------------------------------------------------------ lollipop */
  // Mirrors site_charts.py's lollipop_chart() -- dot-and-stem, reserved for
  // market comparisons so they read visually distinct from the filled bars
  // used for channel comparisons on the same page.
  function lollipopChart(labels, values, opts) {
    opts = opts || {};
    var n = labels.length, row = opts.rowHeight || 34;
    var padL = 152, padR = 56, padT = 8, padB = 22;
    var width = opts.width || 760;
    var height = opts.height || (padT + padB + row * n);
    var pw = width - padL - padR;
    var colors = opts.colors || labels.map(function () { return SERIES[0]; });
    var vFmt = opts.vFmt || num;
    var lo = Math.min(0, Math.min.apply(null, values));
    var hi = Math.max.apply(null, values);
    if (hi === lo) hi = lo + 1;
    var pad = (hi - lo) * 0.06; hi += pad; if (lo < 0) lo -= pad;
    function X(v) { return padL + (v - lo) / (hi - lo) * pw; }
    var xZero = lo < 0 ? X(0) : padL;

    var out = ['<svg class="chart" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="xMidYMid meet" data-chart="' + esc(opts.chartId || 'lol') + '" role="img">'];
    for (var i = 0; i < n; i++) {
      var lab = labels[i], v = values[i], c = colors[i];
      var y = padT + i * row + row / 2 - 3;
      var x2 = X(v);
      var fattrs = fAttrs(opts.filterDim, _fval(opts, i, lab));
      out.push('<line x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (width - padR) + '" y2="' + y.toFixed(1) + '" stroke="' + GRID + '" stroke-width="1"/>');
      out.push('<line x1="' + xZero.toFixed(1) + '" y1="' + y.toFixed(1) + '" x2="' + x2.toFixed(1) + '" y2="' + y.toFixed(1) + '" stroke="' + c + '" stroke-width="2.5"' + fattrs + '/>');
      out.push('<circle cx="' + x2.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="5.5" fill="' + c + '" stroke="#fff" stroke-width="1.5" class="bar" data-title="' + esc(lab) + '" data-body="' + esc(vFmt(v)) + '"' + fattrs + '/>');
      out.push('<text x="' + (padL - 12) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end" class="cat">' + esc(lab) + '</text>');
      var text = vFmt(v), wEst = text.length * 6.7;
      var tx, anchor, fill;
      if (x2 + 11 + wEst > width - 4) { tx = x2 - 10; anchor = 'end'; fill = '#ffffff'; }
      else { tx = x2 + 11; anchor = 'start'; fill = INK_2; }
      out.push('<text x="' + tx.toFixed(1) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="' + anchor + '" class="val" fill="' + fill + '">' + esc(text) + '</text>');
    }
    out.push('</svg>');
    return out.join('');
  }

  /* --------------------------------------------------------------- donut */
  // Mirrors site_charts.py's donut_chart() -- part-of-whole with a centred
  // total, kept distinct from pieChart() (reserved for the Channels page's
  // click-to-drill-down pie).
  function donutChart(labels, values, opts) {
    opts = opts || {};
    var n = labels.length;
    var colors = opts.colors || labels.map(function (_, i) { return SERIES[i % SERIES.length]; });
    var vFmt = opts.vFmt || num;
    var size = opts.size || 300;
    var hole = opts.hole || 0.6;
    var total = values.reduce(function (a, b) { return a + b; }, 0) || 1;
    var cx = size / 2, cy = size / 2, rOut = size / 2 - 6, rIn = rOut * hole;

    var svg = ['<svg class="chart chart-pie" viewBox="0 0 ' + size + ' ' + size + '" preserveAspectRatio="xMidYMid meet" data-chart="' + esc(opts.chartId || 'donut') + '" role="img">'];
    var legendItems = [];
    var angle = -90;
    for (var i = 0; i < n; i++) {
      var lab = labels[i], v = values[i], c = colors[i];
      var frac = v / total, sweep = frac * 360;
      var a0 = angle * Math.PI / 180, a1 = (angle + sweep) * Math.PI / 180;
      var ox1 = cx + rOut * Math.cos(a0), oy1 = cy + rOut * Math.sin(a0);
      var ox2 = cx + rOut * Math.cos(a1), oy2 = cy + rOut * Math.sin(a1);
      var ix1 = cx + rIn * Math.cos(a1), iy1 = cy + rIn * Math.sin(a1);
      var ix2 = cx + rIn * Math.cos(a0), iy2 = cy + rIn * Math.sin(a0);
      var large = sweep > 180 ? 1 : 0;
      var fattrs = fAttrs(opts.filterDim, _fval(opts, i, lab));
      svg.push('<path class="pie-slice" d="M' + ox1.toFixed(2) + ',' + oy1.toFixed(2) +
        ' A' + rOut.toFixed(1) + ',' + rOut.toFixed(1) + ' 0 ' + large + ',1 ' + ox2.toFixed(2) + ',' + oy2.toFixed(2) +
        ' L' + ix1.toFixed(2) + ',' + iy1.toFixed(2) + ' A' + rIn.toFixed(1) + ',' + rIn.toFixed(1) + ' 0 ' + large + ',0 ' +
        ix2.toFixed(2) + ',' + iy2.toFixed(2) + ' Z" fill="' + c + '" data-title="' + esc(lab) +
        '" data-body="' + esc(vFmt(v)) + ' · ' + (frac * 100).toFixed(1) + '% of total"' + fattrs + '/>');
      legendItems.push('<span class="pie-legend-item"' + fattrs + '>' +
        '<span class="lg-dot" style="background:' + c + '"></span>' +
        '<span class="pli-label">' + esc(lab) + '</span>' +
        '<span class="pli-share">' + (frac * 100).toFixed(0) + '%</span></span>');
      angle += sweep;
    }
    svg.push('</svg>');
    var center = '';
    if (opts.centerLabel) {
      center = '<div class="donut-center"><div class="donut-center-val">' + esc(opts.centerLabel) + '</div>' +
        '<div class="donut-center-sub">' + esc(opts.centerSub || '') + '</div></div>';
    }
    return '<div class="pie-block"><div class="pie-svg-wrap donut-wrap">' + svg.join('') + center + '</div>' +
      '<div class="pie-legend">' + legendItems.join('') + '</div></div>';
  }

  /* ----------------------------------------------------- grouped h bars */
  function groupedBarH(labels, series, opts) {
    // series: [[name, values[], color], ...]
    opts = opts || {};
    var n = labels.length, k = series.length, row = 40;
    var padL = 152, padR = 62, padT = 8, padB = 18;
    var width = opts.width || 760;
    var height = padT + padB + row * n;
    var pw = width - padL - padR;
    var vFmt = opts.vFmt || pct;
    var labelSeries = ((opts.labelSeries === undefined ? -1 : opts.labelSeries) % k + k) % k;
    var hi = 0;
    series.forEach(function (s) { s[1].forEach(function (v) { if (v > hi) hi = v; }); });
    hi = (hi || 1) * 1.04;

    var out = ['<svg class="chart" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="xMidYMid meet" data-chart="' + esc(opts.chartId || 'g') + '" role="img">'];
    var barH = (row - 16) / k;
    for (var i = 0; i < n; i++) {
      var lab = labels[i];
      var y0 = padT + i * row + 8;
      out.push('<text x="' + (padL - 12) + '" y="' + (y0 + (row - 16) / 2 + 4).toFixed(1) + '" text-anchor="end" class="cat">' + esc(lab) + '</text>');
      for (var j = 0; j < k; j++) {
        var sname = series[j][0], vals = series[j][1], color = series[j][2];
        var v = vals[i];
        var y = y0 + j * barH + (j ? 1 : 0);
        var w = Math.max(v / hi * pw, 1.5);
        out.push('<rect x="' + padL + '" y="' + y.toFixed(1) + '" width="' + w.toFixed(1) + '" height="' + (barH - 2).toFixed(1) +
          '" rx="2.5" fill="' + color + '" class="bar" data-title="' + esc(lab) + '" data-body="' + esc(sname) + ': ' + esc(vFmt(v)) + '"' +
          fAttrs(opts.filterDim, lab) + '/>');
      }
      var lv = series[labelSeries][1][i];
      out.push('<text x="' + (padL + lv / hi * pw + 8).toFixed(1) + '" y="' + (y0 + (row - 16) / 2 + 4).toFixed(1) +
        '" class="val">' + esc(vFmt(lv)) + '</text>');
    }
    out.push('</svg>');
    return out.join('');
  }

  /* ----------------------------------------------------------- line chart */
  function lineChart(xLabels, series, opts) {
    // series: [{label, values[], color, width, dashed}]
    opts = opts || {};
    var padL = 58, padR = 18, padT = 16, padB = 34;
    var width = opts.width || 760, height = opts.height || 300;
    var pw = width - padL - padR, ph = height - padT - padB;
    var yFmt = opts.yFmt || num;
    var hoverFmt = opts.hoverFmt || yFmt;

    var flat = [];
    series.forEach(function (s) { s.values.forEach(function (v) { if (v !== null && v !== undefined && !isNaN(v)) flat.push(v); }); });
    var lo = flat.length ? Math.min.apply(null, flat) : 0;
    var hi = flat.length ? Math.max.apply(null, flat) : 1;
    if (opts.yZero) lo = Math.min(lo, 0);
    var span = (hi - lo) || 1;
    lo -= span * 0.08; hi += span * 0.08;
    var ticks = niceTicks(lo, hi);
    lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);

    var n = xLabels.length;
    function X(i) { return padL + (pw * i / Math.max(n - 1, 1)); }
    function Y(v) { return padT + ph - (v - lo) / (hi - lo) * ph; }

    var out = ['<svg class="chart" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="xMidYMid meet" data-chart="' + esc(opts.chartId || 'l') + '" role="img">'];

    ticks.forEach(function (t) {
      if (t < lo || t > hi) return;
      var y = Y(t);
      out.push('<line x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (width - padR) + '" y2="' + y.toFixed(1) + '" stroke="' + GRID + '" stroke-width="1"/>');
      out.push('<text x="' + (padL - 10) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end" class="tick">' + esc(yFmt(t)) + '</text>');
    });

    var step = Math.max(1, Math.floor(n / 7));
    for (var i = 0; i < n; i += step) {
      out.push('<text x="' + X(i).toFixed(1) + '" y="' + (height - 12) + '" text-anchor="middle" class="tick">' + esc(xLabels[i]) + '</text>');
    }

    out.push('<line x1="' + padL + '" y1="' + (padT + ph) + '" x2="' + (width - padR) + '" y2="' + (padT + ph) + '" stroke="' + BASELINE + '" stroke-width="1"/>');

    // seriesFilterDim makes each SERIES (e.g. one line per market) a click
    // target, via a marker circle at every point plus the stroke itself -- a
    // thin stroke alone is an unreliable click target. Mutually exclusive with
    // filterDim below, which instead makes each WEEK (the x-axis) clickable;
    // a chart isn't both at once.
    series.forEach(function (s) {
      var idxPts = [];
      s.values.forEach(function (v, idx) {
        if (v !== null && v !== undefined && !isNaN(v)) idxPts.push([idx, X(idx), Y(v)]);
      });
      if (!idxPts.length) return;
      var fval = s.filterVal !== undefined && s.filterVal !== null ? s.filterVal : s.label;
      var sfAttrs = opts.seriesFilterDim ? fAttrs(opts.seriesFilterDim, fval) : '';
      var dash = s.dashed ? ' stroke-dasharray="5 4"' : '';
      var pts = idxPts.map(function (p) { return p[1].toFixed(1) + ',' + p[2].toFixed(1); }).join(' ');
      out.push('<polyline points="' + pts + '" fill="none" stroke="' + (s.color || SERIES[0]) +
        '" stroke-width="' + (s.width || 2) + '" stroke-linecap="round" stroke-linejoin="round"' + dash + sfAttrs + '/>');
      // White-centre, coloured-ring point markers on every line, ported from
      // the reference's lineChart()/comboChart() -- drawn regardless of
      // whether the series is a click-to-filter target.
      idxPts.forEach(function (p) {
        out.push('<circle cx="' + p[1].toFixed(1) + '" cy="' + p[2].toFixed(1) + '" r="3.2" fill="#fff" stroke="' + (s.color || SERIES[0]) +
          '" stroke-width="1.8" data-title="' + esc(s.label) + '" data-body="' +
          esc(xLabels[p[0]] + ': ' + hoverFmt(s.values[p[0]])) + '"' + sfAttrs + '/>');
      });
    });

    out.push('<g class="hit" data-n="' + n + '">');
    var bw = pw / Math.max(n - 1, 1);
    for (var i2 = 0; i2 < n; i2++) {
      var payload = series.filter(function (s) { return s.values[i2] !== null && s.values[i2] !== undefined && !isNaN(s.values[i2]); })
        .map(function (s) { return s.label + ': ' + hoverFmt(s.values[i2]); }).join(' · ');
      var weekFAttrs = opts.seriesFilterDim ? '' : fAttrs(opts.filterDim, opts.filterVals ? opts.filterVals[i2] : null);
      out.push('<rect x="' + (X(i2) - bw / 2).toFixed(1) + '" y="' + padT + '" width="' + bw.toFixed(1) + '" height="' + ph +
        '" fill="transparent" data-x="' + X(i2).toFixed(1) + '" data-y0="' + padT + '" data-y1="' + (padT + ph) +
        '" data-title="' + esc(xLabels[i2]) + '" data-body="' + esc(payload) + '"' + weekFAttrs + '/>');
    }
    out.push('</g>');
    out.push('<line class="crosshair" x1="0" y1="' + padT + '" x2="0" y2="' + (padT + ph) + '" stroke="' + BASELINE + '" stroke-width="1" opacity="0"/>');
    out.push('</svg>');
    return out.join('');
  }

  /* -------------------------------------------------------------- kpi card */
  function sparklineSvg(values, color) {
    var vals = (values || []).filter(function (v) { return v !== null && v !== undefined && !isNaN(v); });
    if (vals.length < 2) return '';
    var w = 120, h = 26, pad = 2;
    var mn = Math.min.apply(null, vals), mx = Math.max.apply(null, vals);
    var rg = (mx - mn) || 1;
    function X(i) { return pad + i * (w - pad * 2) / (vals.length - 1); }
    function Y(v) { return h - pad - (v - mn) / rg * (h - pad * 2); }
    var pts = vals.map(function (v, i) { return [X(i), Y(v)]; });
    var line = pts.map(function (p, i) { return (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
    var area = line + ' L' + pts[pts.length - 1][0].toFixed(1) + ' ' + h + ' L' + pts[0][0].toFixed(1) + ' ' + h + ' Z';
    var gid = 'sg' + Math.abs(Math.round(mn * 1000 + mx * 1000 + vals.length)) % 100000;
    var last = pts[pts.length - 1];
    return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none">' +
      '<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="' + color + '" stop-opacity=".24"/>' +
      '<stop offset="100%" stop-color="' + color + '" stop-opacity="0"/></linearGradient></defs>' +
      '<path d="' + area + '" fill="url(#' + gid + ')"/>' +
      '<path d="' + line + '" fill="none" stroke="' + color + '" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>' +
      '<circle cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) + '" r="2.4" fill="' + color + '"/></svg>';
  }
  /* One small outline-icon vocabulary for every KPI tile -- see
     build_site.py's _ICONS/_kpi_icon for why (colour via currentColor from
     --k-accent, matched by what the number is before what the label says). */
  var ICON_ATTRS = 'width="15" height="15" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="kpi-icon"';
  var ICONS = {
    currency: '<svg ' + ICON_ATTRS + '><rect x="2" y="5" width="14" height="8" rx="1.5"/><circle cx="9" cy="9" r="1.8"/></svg>',
    percent: '<svg ' + ICON_ATTRS + '><circle cx="5.5" cy="5.5" r="1.6"/><circle cx="12.5" cy="12.5" r="1.6"/><path d="M13 5 5 13"/></svg>',
    trend: '<svg ' + ICON_ATTRS + '><path d="M3 13l4-4 3 3 6-7"/><path d="M12.5 4.5H16v3.5"/></svg>',
    alert: '<svg ' + ICON_ATTRS + '><path d="M9 3 16 15H2Z"/><path d="M9 7.5v3"/><circle cx="9" cy="12.3" r=".9" fill="currentColor" stroke="none"/></svg>',
    people: '<svg ' + ICON_ATTRS + '><circle cx="9" cy="6" r="2.3"/><path d="M4 15c0-3 2.3-5 5-5s5 2 5 5"/></svg>',
    table: '<svg ' + ICON_ATTRS + '><rect x="2.5" y="2.5" width="13" height="13" rx="1.5"/><path d="M2.5 9h13M9 2.5v13"/></svg>',
    check: '<svg ' + ICON_ATTRS + '><circle cx="9" cy="9" r="6.5"/><path d="M5.8 9.2l2.1 2.1 4.3-4.6"/></svg>',
    rows: '<svg ' + ICON_ATTRS + '><path d="M3 5h12M3 9h12M3 13h12"/></svg>',
    broadcast: '<svg ' + ICON_ATTRS + '><circle cx="9" cy="12" r="1.6"/><path d="M5.5 10.5a5 5 0 017 0M3 7.8a9 9 0 0112 0"/></svg>',
    hash: '<svg ' + ICON_ATTRS + '><path d="M6.2 3 4.6 15M13.4 3 11.8 15M3 7.3h12M2.4 10.7h12"/></svg>'
  };
  function kpiIcon(label, value, unit) {
    if (String(value).indexOf('AED') >= 0) return ICONS.currency;
    if (unit === 'x') return ICONS.trend;
    if (unit === '%') return ICONS.percent;
    var low = label.toLowerCase();
    if (low.indexOf('influencer') >= 0) return ICONS.people;
    if (low.indexOf('table') >= 0) return ICONS.table;
    if (low.indexOf('check') >= 0) return ICONS.check;
    if (low.indexOf('row') >= 0) return ICONS.rows;
    if (low.indexOf('grp') >= 0) return ICONS.broadcast;
    if (low.indexOf('alert') >= 0 || low.indexOf('fired') >= 0 ||
        low === 'critical' || low === 'high' || low === 'medium' || low === 'open now') return ICONS.alert;
    return ICONS.hash;
  }
  function kpiCard(opts) {
    // {label, value, unit, delta (fraction), goodUp, vs, spark[], sparkColor}
    // -- delta/vs/spark are opt-in per call site; most just pass label/value/unit.
    var foot = '';
    if (opts.delta !== null && opts.delta !== undefined && !isNaN(opts.delta)) {
      var up = opts.delta >= 0;
      var cls = (up === (opts.goodUp !== false)) ? 'up' : 'down';
      var arrow = up ? '▲' : '▼';
      foot = '<div class="foot"><span class="delta ' + cls + '">' + arrow + ' ' +
        Math.abs(opts.delta * 100).toFixed(1) + '%</span><span class="vs">' + esc(opts.vs || 'vs prior period') + '</span></div>';
    }
    var unitHtml = opts.unit ? '<span class="u"> ' + esc(opts.unit) + '</span>' : '';
    var sparkHtml = (opts.spark && opts.spark.length) ? sparklineSvg(opts.spark, opts.sparkColor || SERIES[0]) : '';
    var icon = kpiIcon(opts.label, opts.value, opts.unit || '');
    return '<div class="kpi">' +
      '<div class="lab">' + icon + esc(opts.label) + '</div>' +
      '<div class="val">' + opts.value + unitHtml + '</div>' + foot + sparkHtml + '</div>';
  }
  function kpiLink(target, kpiHtml, external) {
    var href = external ? target : ('#' + target);
    return '<a class="kpi-link" href="' + esc(href) + '">' + kpiHtml + '</a>';
  }

  // Mirrors build_site.py's kpi_select() -- a click-to-select KPI card
  // (Overview page) rather than a jump-to-anchor one. Same display:contents
  // wrapper class as kpiLink, plus data-kpi for the click handler and
  // .selected for the highlighted-card outline.
  function kpiSelect(key, kpiHtml, selected) {
    return '<button type="button" class="kpi-link' + (selected ? ' selected' : '') +
      '" data-kpi="' + esc(key) + '">' + kpiHtml + '</button>';
  }

  /* -------------------------------------------------------------- table */
  function table(rows, cols, formats, opts) {
    // cols: [{key, label, fmt}], formats optional per-col override.
    // opts.sortable adds data-sort/data-i so app.js's enhanceSortableTables
    // can wire click-to-sort headers onto the result.
    var sortable = !!(opts && opts.sortable);
    var ths = cols.map(function (c, i) {
      var cls = (c.fmt ? 'num' : '') + (sortable ? ' sort-h' : '');
      return '<th class="' + cls.trim() + '"' + (sortable ? ' data-i="' + i + '"' : '') +
        '>' + esc(c.label || c.key.replace(/_/g, ' ')) + '</th>';
    }).join('');
    var trs = rows.map(function (r) {
      var tds = cols.map(function (c) {
        var v = r[c.key];
        var sortAttr = sortable && v !== null && v !== undefined
          ? ' data-sort="' + esc(v) + '"' : '';
        if (c.fmt) {
          var cls = 'num' + (c.cls ? ' ' + c.cls(v) : '');
          var txt = (v === null || v === undefined) ? '—' : c.fmt(v);
          return '<td class="' + cls + '"' + sortAttr + '>' + txt + '</td>';
        }
        return '<td' + sortAttr + '>' + ((v === null || v === undefined) ? '—' : esc(v)) + '</td>';
      }).join('');
      return '<tr>' + tds + '</tr>';
    }).join('');
    var wrapCls = 'table-wrap' + (sortable ? ' sortable-table' : '');
    return '<div class="' + wrapCls + '"><table><thead><tr>' + ths + '</tr></thead><tbody>' + trs + '</tbody></table></div>';
  }
  function tableView(rows, cols, label) {
    return '<details class="table-view"><summary>' + esc(label || 'View as table') + '</summary>' + table(rows, cols) + '</details>';
  }

  /* ----------------------------------------------------- stacked columns */
  function stackedColumns(xLabels, series, opts) {
    // series: [[name, values[], color], ...]
    opts = opts || {};
    var padL = 46, padR = 16, padT = 14, padB = 34;
    var width = opts.width || 760, height = opts.height || 280;
    var pw = width - padL - padR, ph = height - padT - padB;
    var n = xLabels.length;
    var vFmt = opts.vFmt || num;
    var totals = [];
    for (var i = 0; i < n; i++) { totals.push(series.reduce(function (a, s) { return a + (s[1][i] || 0); }, 0)); }
    var hi = Math.max.apply(null, totals) || 1;
    var ticks = niceTicks(0, hi, 4);
    hi = Math.max(hi, ticks[ticks.length - 1]);

    var out = ['<svg class="chart" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="xMidYMid meet" data-chart="' + esc(opts.chartId || 'sc') + '" role="img">'];
    ticks.forEach(function (t) {
      var y = padT + ph - t / hi * ph;
      out.push('<line x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (width - padR) + '" y2="' + y.toFixed(1) + '" stroke="' + GRID + '" stroke-width="1"/>');
      out.push('<text x="' + (padL - 8) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end" class="tick">' + esc(vFmt(t)) + '</text>');
    });

    var cw = pw / Math.max(n, 1);
    var bw = Math.min(cw * 0.62, 18);
    for (var j = 0; j < n; j++) {
      var cx = padL + cw * (j + 0.5);
      var acc = 0;
      series.forEach(function (s) {
        var v = s[1][j];
        if (!v || v <= 0) return;
        var h = v / hi * ph;
        var y = padT + ph - (acc + v) / hi * ph;
        out.push('<rect x="' + (cx - bw / 2).toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) +
          '" height="' + Math.max(h - 2, 1).toFixed(1) + '" rx="2" fill="' + s[2] + '" class="bar" data-title="' +
          esc(xLabels[j]) + '" data-body="' + esc(s[0]) + ': ' + esc(vFmt(v)) + '"' + fAttrs(opts.filterDim, s[0]) + '/>');
        acc += v;
      });
    }
    var step = Math.max(1, Math.floor(n / 8));
    for (var k = 0; k < n; k += step) {
      out.push('<text x="' + (padL + cw * (k + 0.5)).toFixed(1) + '" y="' + (height - 12) + '" text-anchor="middle" class="tick">' + esc(xLabels[k]) + '</text>');
    }
    out.push('<line x1="' + padL + '" y1="' + (padT + ph) + '" x2="' + (width - padR) + '" y2="' + (padT + ph) + '" stroke="' + BASELINE + '" stroke-width="1"/>');
    out.push('</svg>');
    return out.join('');
  }

  /* ------------------------------------------------------ graded bar chart */
  // Single-series vertical bars, coloured and annotated per bar -- see
  // site_charts.py's bar_chart_graded for why this needed its own primitive
  // rather than reusing stackedColumns.
  function barChartGraded(xLabels, values, colors, tooltipTitles, tooltipBodies, opts) {
    opts = opts || {};
    var padL = 46, padR = 16, padT = 14, padB = 34;
    var width = opts.width || 760, height = opts.height || 280;
    var pw = width - padL - padR, ph = height - padT - padB;
    var n = xLabels.length;
    var vFmt = opts.vFmt || num;
    var hi = Math.max.apply(null, values) || 1;
    var ticks = niceTicks(0, hi, 4);
    hi = Math.max(hi, ticks[ticks.length - 1]) || 1;

    var out = ['<svg class="chart" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="xMidYMid meet" data-chart="' + esc(opts.chartId || 'bcg') + '" role="img">'];
    ticks.forEach(function (t) {
      var y = padT + ph - t / hi * ph;
      out.push('<line x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (width - padR) + '" y2="' + y.toFixed(1) + '" stroke="' + GRID + '" stroke-width="1"/>');
      out.push('<text x="' + (padL - 8) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end" class="tick">' + esc(vFmt(t)) + '</text>');
    });

    var cw = pw / Math.max(n, 1);
    var bw = Math.min(cw * 0.62, 22);
    for (var i = 0; i < n; i++) {
      var cx = padL + cw * (i + 0.5);
      var v = Math.max(values[i] || 0, 0);
      var h = v / hi * ph;
      var y = padT + ph - h;
      out.push('<rect x="' + (cx - bw / 2).toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) +
        '" height="' + Math.max(h, 1).toFixed(1) + '" rx="2" fill="' + colors[i] + '" class="bar" data-title="' +
        esc(tooltipTitles[i]) + '" data-body="' + esc(tooltipBodies[i]) + '"/>');
    }
    for (var k = 0; k < n; k++) {
      out.push('<text x="' + (padL + cw * (k + 0.5)).toFixed(1) + '" y="' + (height - 12) + '" text-anchor="middle" class="tick">' + esc(xLabels[k]) + '</text>');
    }
    out.push('<line x1="' + padL + '" y1="' + (padT + ph) + '" x2="' + (width - padR) + '" y2="' + (padT + ph) + '" stroke="' + BASELINE + '" stroke-width="1"/>');
    out.push('</svg>');
    return out.join('');
  }

  /* ------------------------------------------------------------- scatter */
  function scatter(points, opts) {
    // points: [{x, y, label, size, detail}]
    opts = opts || {};
    var padL = 66, padR = 30, padT = 34, padB = 48;
    var width = opts.width || 760, height = opts.height || 460;
    var pw = width - padL - padR, ph = height - padT - padB;
    var xFmtF = opts.xFmt || num, yFmtF = opts.yFmt || num;
    var xLabel = opts.xLabel || '', yLabel = opts.yLabel || '';

    var xs = points.map(function (p) { return p.x; }), ys = points.map(function (p) { return p.y; });
    var xlo = Math.min.apply(null, xs), xhi = Math.max.apply(null, xs);
    var ylo = Math.min.apply(null, ys), yhi = Math.max.apply(null, ys);
    var xspan = (xhi - xlo) || 1, yspan = (yhi - ylo) || 1;
    if (opts.xPadFrac !== undefined && opts.xPadFrac !== null) {
      xlo -= xspan * opts.xPadFrac; xhi += xspan * opts.xPadFrac;
      if (Math.min.apply(null, xs) >= 0) xlo = Math.max(xlo, 0);
    } else {
      xlo -= xspan * 0.10; xhi += xspan * 0.08;
    }
    ylo -= yspan * 0.12; yhi += yspan * 0.16;
    function X(v) { return padL + (v - xlo) / (xhi - xlo) * pw; }
    function Y(v) { return padT + ph - (v - ylo) / (yhi - ylo) * ph; }

    var out = ['<svg class="chart" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="xMidYMid meet" data-chart="' + esc(opts.chartId || 's') + '" role="img">'];

    if (opts.quadrantFill && opts.xMed !== undefined && opts.yMed !== undefined) {
      var qmx = X(opts.xMed), qmy = Y(opts.yMed);
      var qx2 = width - padR, qy2 = height - padB;
      out.push('<rect x="' + padL.toFixed(1) + '" y="' + padT.toFixed(1) + '" width="' + (qmx - padL).toFixed(1) + '" height="' + (qmy - padT).toFixed(1) + '" fill="#EDF7F1" opacity=".75"/>');
      out.push('<rect x="' + qmx.toFixed(1) + '" y="' + padT.toFixed(1) + '" width="' + (qx2 - qmx).toFixed(1) + '" height="' + (qmy - padT).toFixed(1) + '" fill="#EAF0FE" opacity=".75"/>');
      out.push('<rect x="' + qmx.toFixed(1) + '" y="' + qmy.toFixed(1) + '" width="' + (qx2 - qmx).toFixed(1) + '" height="' + (qy2 - qmy).toFixed(1) + '" fill="#FDECEC" opacity=".6"/>');
      out.push('<rect x="' + padL.toFixed(1) + '" y="' + qmy.toFixed(1) + '" width="' + (qmx - padL).toFixed(1) + '" height="' + (qy2 - qmy).toFixed(1) + '" fill="#F5F6F8" opacity=".8"/>');
    }

    niceTicks(ylo, yhi, 5).forEach(function (t) {
      if (t < ylo || t > yhi) return;
      var y = padT + ph - (t - ylo) / (yhi - ylo) * ph;
      out.push('<line x1="' + padL + '" y1="' + y.toFixed(1) + '" x2="' + (width - padR) + '" y2="' + y.toFixed(1) + '" stroke="' + GRID + '" stroke-width="1"/>');
      out.push('<text x="' + (padL - 10) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end" class="tick">' + esc(yFmtF(t)) + '</text>');
    });
    niceTicks(xlo, xhi, 5).forEach(function (t) {
      if (t < xlo || t > xhi) return;
      out.push('<text x="' + X(t).toFixed(1) + '" y="' + (height - 26) + '" text-anchor="middle" class="tick">' + esc(xFmtF(t)) + '</text>');
    });

    if (opts.xMed !== undefined) {
      out.push('<line x1="' + X(opts.xMed).toFixed(1) + '" y1="' + padT + '" x2="' + X(opts.xMed).toFixed(1) + '" y2="' + (padT + ph) + '" stroke="' + BASELINE + '" stroke-width="1"/>');
    }
    if (opts.yMed !== undefined) {
      out.push('<line x1="' + padL + '" y1="' + Y(opts.yMed).toFixed(1) + '" x2="' + (width - padR) + '" y2="' + Y(opts.yMed).toFixed(1) + '" stroke="' + BASELINE + '" stroke-width="1"/>');
    }
    if (opts.diagonal) {
      var lim = Math.min(xhi, yhi);
      out.push('<line x1="' + X(0).toFixed(1) + '" y1="' + Y(0).toFixed(1) + '" x2="' + X(lim).toFixed(1) + '" y2="' + Y(lim).toFixed(1) +
        '" stroke="' + BASELINE + '" stroke-width="1.2" stroke-dasharray="4 4"/>');
    }

    var smax = Math.max.apply(null, points.map(function (p) { return p.size || 1; })) || 1;
    points.forEach(function (p) {
      var r = opts.sizeScale === 'sqrt'
        ? 5 + Math.sqrt((p.size || 1) / smax) * 20
        : 6 + ((p.size || 1) / smax) * 16;
      var cx = X(p.x), cy = Y(p.y);
      var body = yLabel + ': ' + yFmtF(p.y) + ' · ' + xLabel + ': ' + xFmtF(p.x) + (p.detail ? ' · ' + p.detail : '');
      var fattrs = opts.filterDim ? fAttrs(opts.filterDim, p.label) : '';
      out.push('<circle cx="' + cx.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="' + r.toFixed(1) + '" fill="' + (p.color || opts.color || SERIES[0]) +
        '" fill-opacity="0.78" class="pt" data-title="' + esc(p.label) + '" data-body="' + esc(body) + '" stroke="#fff" stroke-width="2"' + fattrs + '/>');
      if (opts.pointLabels) {
        out.push('<text x="' + cx.toFixed(1) + '" y="' + (cy - r - 6).toFixed(1) + '" text-anchor="middle" class="ann">' + esc(p.label) + '</text>');
      }
    });

    out.push('<text x="' + (padL + pw / 2).toFixed(1) + '" y="' + (height - 6) + '" text-anchor="middle" class="axis-title">' + esc(xLabel) + '</text>');
    out.push('<text x="16" y="' + (padT + ph / 2).toFixed(1) + '" text-anchor="middle" class="axis-title" transform="rotate(-90 16 ' + (padT + ph / 2).toFixed(1) + ')">' + esc(yLabel) + '</text>');
    out.push('</svg>');
    return out.join('');
  }

  /* ------------------------------------------------------------- heatmap */
  var SEQ_BLUE = ['#e8eefc', '#cddafa', '#a9c1f3', '#7fa2ea', '#5581df', '#3a63d6', '#2f4bd4'];
  var DIV_RED_BLUE = ['#b03030', '#cf6a5a', '#e8a898', '#efefec', '#9fb6e8', '#5f83db', '#2f4bd4'];

  function heatmap(rowLabels, colLabels, values, opts) {
    // values[i][j] for row i, col j. opts.filterDim makes each cell a click
    // target on its COLUMN value (matches every existing "click a cell to
    // filter to that channel" chart -- rows are products/markets, which aren't
    // filter dimensions here).
    opts = opts || {};
    var padL = 152, padR = 16, padT = 46, padB = 34;
    var cellH = 38;
    var width = opts.width || 760;
    var height = padT + padB + cellH * rowLabels.length;
    var cw = (width - padL - padR) / Math.max(colLabels.length, 1);
    var vFmt = opts.vFmt || function (v) { return v.toFixed(2); };
    var center = opts.center || 0;

    var flat = [];
    values.forEach(function (row) { row.forEach(function (v) { if (v !== null && v !== undefined && !isNaN(v)) flat.push(v); }); });
    var lo = flat.length ? Math.min.apply(null, flat) : 0, hi = flat.length ? Math.max.apply(null, flat) : 1;
    var rng = (hi - lo) || 1;
    var half = Math.max(Math.abs(hi - center), Math.abs(center - lo)) || 1;

    function colorFor(v) {
      if (v === null || v === undefined || isNaN(v)) return '#f4f4f2';
      if (opts.diverging) {
        var t = (v - center) / half;
        var idx = Math.round((t + 1) / 2 * (DIV_RED_BLUE.length - 1));
        return DIV_RED_BLUE[Math.max(0, Math.min(DIV_RED_BLUE.length - 1, idx))];
      }
      var idx2 = Math.floor((v - lo) / rng * (SEQ_BLUE.length - 1));
      return SEQ_BLUE[Math.max(0, Math.min(SEQ_BLUE.length - 1, idx2))];
    }

    var out = ['<svg class="chart" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="xMidYMid meet" data-chart="' + esc(opts.chartId || 'hm') + '" role="img">'];
    colLabels.forEach(function (cl, j) {
      out.push('<text x="' + (padL + cw * (j + 0.5)).toFixed(1) + '" y="' + (padT - 14) + '" text-anchor="middle" class="tick">' + esc(cl) + '</text>');
    });
    rowLabels.forEach(function (rl, i) {
      var y = padT + i * cellH;
      out.push('<text x="' + (padL - 12) + '" y="' + (y + cellH / 2 + 4).toFixed(1) + '" text-anchor="end" class="cat">' + esc(rl) + '</text>');
      colLabels.forEach(function (cl, j) {
        var v = values[i][j];
        var fill = colorFor(v);
        var fattrs = opts.filterDim ? fAttrs(opts.filterDim, cl) : '';
        var known = v !== null && v !== undefined && !isNaN(v);
        out.push('<rect x="' + (padL + cw * j + 1).toFixed(1) + '" y="' + (y + 1).toFixed(1) + '" width="' + (cw - 2).toFixed(1) +
          '" height="' + (cellH - 2) + '" rx="3" fill="' + fill + '" class="bar" data-title="' + esc(rl) + ' · ' + esc(cl) +
          '" data-body="' + esc(known ? vFmt(v) : 'no data') + '"' + fattrs + '/>');
        if (known) {
          var dark = opts.diverging ? (Math.abs(v - center) / half > 0.62) : ((v - lo) / rng > 0.62);
          out.push('<text x="' + (padL + cw * (j + 0.5)).toFixed(1) + '" y="' + (y + cellH / 2 + 4).toFixed(1) +
            '" text-anchor="middle" class="val" fill="' + (dark ? '#ffffff' : INK_2) + '">' + esc(vFmt(v)) + '</text>');
        }
      });
    });
    if (opts.scaleLabel) {
      out.push('<text x="' + padL + '" y="' + (height - 10) + '" class="tick">' + esc(opts.scaleLabel) + '</text>');
    }
    out.push('</svg>');
    return out.join('');
  }

  /* ------------------------------------------------------------- funnel */
  function funnelChart(stages, chartId) {
    // stages: [{ stage, value, source }], top-to-bottom. Geometry mirrors
    // site_charts.py's funnel_chart() -- trapezoids sized by sqrt(value)
    // against the top stage, shaded from the reference's funnelChart().
    var W = 900, rowH = 62, H = stages.length * rowH + 16;
    var maxV = stages[0].value || 1, cx = W / 2, maxW = 520;
    var shades = ['#1428A0', '#2B4FC4', '#4A7DE0', '#6D9BEC'];
    var out = ['<svg class="chart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="xMinYMin meet" data-chart="' +
      esc(chartId || 'fun') + '" role="img">'];
    stages.forEach(function (st, i) {
      var y = i * rowH + 8;
      var w = Math.max(70, Math.sqrt(st.value / maxV) * maxW);
      var nv = i < stages.length - 1 ? stages[i + 1].value : st.value;
      var nx = Math.max(70, Math.sqrt(nv / maxV) * maxW);
      var shade = shades[i] || '#8FB4F2';
      var step = i === 0 ? null : (stages[i - 1].value ? st.value / stages[i - 1].value * 100 : null);
      var pctTop = maxV ? st.value / maxV * 100 : 0;
      var tip = 'Volume: ' + Math.round(st.value).toLocaleString() + '<br>Of impressions: ' + pctTop.toFixed(2) +
        '%<br>Step rate: ' + (step === null ? '—' : step.toFixed(2) + '%') + '<br>Source: ' + esc(st.source || '');
      out.push('<path d="M' + (cx - w / 2).toFixed(1) + ' ' + y + ' L' + (cx + w / 2).toFixed(1) + ' ' + y +
        ' L' + (cx + nx / 2).toFixed(1) + ' ' + (y + rowH - 14).toFixed(1) + ' L' + (cx - nx / 2).toFixed(1) +
        ' ' + (y + rowH - 14).toFixed(1) + ' Z" fill="' + shade + '" fill-opacity=".92" data-title="' +
        esc(st.stage) + '" data-body="' + tip + '"/>');
      out.push('<text x="' + cx.toFixed(1) + '" y="' + (y + 21).toFixed(1) + '" text-anchor="middle" class="fun-label">' +
        esc(st.stage) + '</text>');
      out.push('<text x="' + cx.toFixed(1) + '" y="' + (y + 37).toFixed(1) + '" text-anchor="middle" class="fun-val">' +
        Math.round(st.value).toLocaleString() + '</text>');
      var rateTxt = i === 0 ? '100%' : (step === null ? '—' : step.toFixed(1) + '%');
      out.push('<text x="' + (cx + maxW / 2 + 30).toFixed(1) + '" y="' + (y + 26).toFixed(1) + '" class="fun-rate">' + rateTxt + '</text>');
      out.push('<text x="' + (cx + maxW / 2 + 30).toFixed(1) + '" y="' + (y + 39).toFixed(1) + '" class="fun-rate-sub">' +
        (i === 0 ? 'entry' : 'of previous stage') + '</text>');
    });
    out.push('</svg>');
    return out.join('');
  }

  return {
    SERIES: SERIES, SERIES_MUTED: SERIES_MUTED, SERIES_PASTEL: SERIES_PASTEL, STATUS: STATUS,
    esc: esc, aed: aed, aedShort: aedShort, xFmt: xFmt, pct: pct, num: num,
    legend: legend, barChartH: barChartH, groupedBarH: groupedBarH, lineChart: lineChart, pieChart: pieChart,
    lollipopChart: lollipopChart, donutChart: donutChart,
    stackedColumns: stackedColumns, barChartGraded: barChartGraded, scatter: scatter, heatmap: heatmap, funnelChart: funnelChart,
    kpiCard: kpiCard, kpiLink: kpiLink, kpiSelect: kpiSelect, sparklineSvg: sparklineSvg, table: table, tableView: tableView
  };
})();
