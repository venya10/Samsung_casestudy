/* Per-page dynamic renderers, called by app_filter.js after every filter
   change with the freshly-fetched table set. Each function only touches the
   #mount-* regions build_site.py wrapped for that page -- the surrounding
   prose (headings, <note> interpretation blocks) stays exactly as Python
   rendered it at build time, since those are findings about the whole
   dataset, not numbers that should reword themselves under a filter. */
(function () {
  'use strict';
  var C = window.Charts;
  var GROSS_MARGIN = 0.22;

  function sum(rows, key) { return rows.reduce(function (a, r) { return a + (r[key] || 0); }, 0); }
  function weeksOf(rows) {
    var ws = {};
    rows.forEach(function (r) { ws[r.week] = true; });
    return Object.keys(ws).map(Number).sort(function (a, b) { return a - b; });
  }
  function avg(vals) { return vals.length ? vals.reduce(function (a, b) { return a + b; }, 0) / vals.length : null; }
  function wow(vals) {
    var clean = vals.filter(function (v) { return v !== null && v !== undefined && !isNaN(v); });
    if (clean.length < 2) return null;
    var mid = Math.ceil(clean.length / 2);
    var prior = avg(clean.slice(0, mid)), cur = avg(clean.slice(mid));
    return prior ? (cur / prior - 1) : null;
  }
  function flagPill(flag) {
    var cls = 'warn', label = 'On par';
    if (flag.indexOf('Strong') === 0) { cls = 'ok'; label = 'Scale'; }
    else if (flag.indexOf('Costly') === 0) { cls = 'bad'; label = 'Costly'; }
    else if (flag.indexOf('Underperforming') === 0) { cls = 'bad'; label = 'Underperforming'; }
    return '<span class="pill ' + cls + '" title="' + C.esc(flag) + '">' + label + '</span>';
  }
  // Same six hues as the pastel cycle each KPI card tints itself with
  // (.kpis .kpi:nth-child(6n+N) in app.css) -- matches src/build_site.py's
  // KPI_ACCENTS exactly, index-for-index by KPI.
  var OV_ACCENTS = ['#7FA8FF', '#6FCFA0', '#F2AD5C', '#B39BF0', '#F291B7', '#62C4C2'];
  function ovXFmt(v) { return v.toFixed(1) + 'x'; }
  function ovPct0(v) { return v.toFixed(0) + '%'; }

  /* -------------------------------------------------- Overview KPI charts */
  // State for the Overview page's KPI-driven 4-chart layout. OV starts as
  // window.__OVERVIEW_DATA__ (baked at build time -- works with no server)
  // and is replaced with a fresh computeOverviewData(t) whenever a live
  // filter change re-runs overview() below. ovKpi persists across both a
  // click and a live refresh, same pattern as Channels' selectedChannel.
  var OV = null;
  var ovKpi = 'sales';

  function renderTrendCard(values, title, sub, vFmt, color, chartId) {
    return '<div class="card"><div class="card-head"><h3>' + title + '</h3>' +
      '<div class="card-sub">' + sub + '</div></div>' +
      C.lineChart(OV.weeks, [{ label: '', values: values, color: color }],
        { yFmt: vFmt, hoverFmt: vFmt, chartId: chartId }) + '</div>';
  }

  // Chart type per (metric, dimension) -- channel comparisons stay bars,
  // market comparisons are lollipops, and product "how it splits" views are
  // donuts (MER/earned-share by product stay lollipops -- a ratio, not a
  // share of a whole, so a donut would misstate it).
  var OV_BREAKDOWN_TYPE = {
    sales: { channel: 'bar', market: 'lollipop', product: 'donut' },
    spend: { channel: 'bar', market: 'lollipop', product: 'donut' },
    mer: { channel: 'bar', market: 'lollipop', product: 'lollipop' },
    earned_share: { market: 'lollipop', product: 'lollipop' },
    unmeasured: { market: 'lollipop', channel: 'bar' }
  };
  var OV_BREAKDOWN_COPY = {
    'sales.channel': ['Which channel earns the sales', 'Sales attributed by channel'],
    'sales.market': ['Which market earns the sales', 'Sales attributed by market'],
    'sales.product': ['How sales split across products', 'Share of total sales, 6 devices'],
    'spend.channel': ['Where the budget is going', 'Spend by channel'],
    'spend.market': ['Where the budget is going, by market', 'Spend by market'],
    'spend.product': ['How the budget splits across products', 'Share of total spend, 6 devices'],
    'mer.channel': ['Which channel returns the most per dirham', 'Sales ÷ spend by channel'],
    'mer.market': ['Which market returns the most per dirham', 'Sales ÷ spend by market'],
    'mer.product': ['Which product returns the most per dirham', 'Sales ÷ spend by product'],
    'earned_share.market': ['Where earned media carries the most weight', 'Earned share of sales, by market'],
    'earned_share.product': ['Which products lean most on earned media', 'Earned share of sales, by product'],
    'unmeasured.market': ['Where the measurement gap is concentrated', 'TV spend by market'],
    'unmeasured.channel': ['Which channel carries the measurement gap', 'Spend with no attributed return, by channel']
  };
  function ovMetricFmt(metric) {
    if (metric === 'mer') return ovXFmt;
    if (metric === 'earned_share') return ovPct0;
    return C.aedShort;
  }

  function renderBreakdownCard(metric, dim) {
    var rows = OV.breakdown[metric][dim];
    var vFmt = ovMetricFmt(metric);
    var labels = rows.map(function (r) { return r.label; });
    var values = rows.map(function (r) { return r.value === null ? 0 : r.value; });
    var fvals = rows.map(function (r) { return r.fval; });
    var type = OV_BREAKDOWN_TYPE[metric][dim];
    var chartId = 'ov-' + metric + '-' + dim;
    var chart;
    if (type === 'bar') {
      chart = C.barChartH(labels, values, { colors: labels.map(function () { return C.SERIES_PASTEL[0]; }), vFmt: vFmt,
        filterDim: dim, filterVals: fvals, chartId: chartId });
    } else if (type === 'lollipop') {
      chart = C.lollipopChart(labels, values, { colors: labels.map(function () { return C.SERIES_PASTEL[5]; }), vFmt: vFmt,
        filterDim: dim, filterVals: fvals, chartId: chartId });
    } else {
      var colors = labels.map(function (_, i) { return C.SERIES_PASTEL[i % C.SERIES_PASTEL.length]; });
      var isSpend = metric === 'spend';
      chart = C.donutChart(labels, values, { colors: colors, vFmt: vFmt, filterDim: dim, filterVals: fvals,
        chartId: chartId, centerLabel: C.aedShort(isSpend ? OV.totals.spend : OV.totals.sales),
        centerSub: isSpend ? 'Total spend' : 'Total sales' });
    }
    var extra = '';
    if (metric === 'mer' && dim === 'channel') {
      extra = '<div class="note"><b>TV</b> <span class="pill bad">Unmeasured</span> — ' +
        Math.round(OV.tv_share_of_spend * 100) + '% of spend, no attributed sales. Excluded from the ' +
        'ranking above, not scored as a zero return.</div>';
    }
    var copy = OV_BREAKDOWN_COPY[metric + '.' + dim];
    return '<div class="card"><div class="card-head"><h3>' + copy[0] + '</h3>' +
      '<div class="card-sub">' + copy[1] + '</div></div>' + chart + extra + '</div>';
  }

  function renderDonutCard(rows, title, sub, colors, chartId, centerLabel, centerSub) {
    var labels = rows.map(function (r) { return r.label; });
    var values = rows.map(function (r) { return r.value === null ? 0 : r.value; });
    return '<div class="card"><div class="card-head"><h3>' + title + '</h3>' +
      '<div class="card-sub">' + sub + '</div></div>' +
      C.donutChart(labels, values, { colors: colors, vFmt: C.aedShort, chartId: chartId,
        centerLabel: centerLabel, centerSub: centerSub }) + '</div>';
  }

  // One entry per KPI card: the four charts it drives.
  var OV_KPIS = {
    sales: {
      chart1: function () { return renderTrendCard(OV.trend.sales, 'Sales across the 8-week cycle', 'Total measured sales, week by week', C.aedShort, OV_ACCENTS[0], 'ov-trend-sales'); },
      chart2: function () { return renderBreakdownCard('sales', 'channel'); },
      chart3: function () { return renderBreakdownCard('sales', 'product'); },
      chart4: function () { return renderBreakdownCard('sales', 'market'); }
    },
    spend: {
      chart1: function () { return renderTrendCard(OV.trend.spend, 'Spend across the 8-week cycle', 'Total media spend, week by week', C.aedShort, OV_ACCENTS[1], 'ov-trend-spend'); },
      chart2: function () { return renderBreakdownCard('spend', 'channel'); },
      chart3: function () { return renderBreakdownCard('spend', 'product'); },
      chart4: function () { return renderBreakdownCard('spend', 'market'); }
    },
    mer: {
      chart1: function () { return renderTrendCard(OV.trend.mer, 'Efficiency across the 8-week cycle', 'Sales per dirham of spend, week by week', ovXFmt, OV_ACCENTS[2], 'ov-trend-mer'); },
      chart2: function () { return renderBreakdownCard('mer', 'channel'); },
      chart3: function () { return renderBreakdownCard('mer', 'product'); },
      chart4: function () { return renderBreakdownCard('mer', 'market'); }
    },
    earned: {
      chart1: function () { return renderTrendCard(OV.trend.earned_share, 'Earned media’s share across the 8-week cycle', 'Share of sales from PR and Website, week by week', ovPct0, OV_ACCENTS[3], 'ov-trend-earned'); },
      chart2: function () { return renderDonutCard(OV.earned_contrib, 'How much of sales media spend actually bought', 'Paid vs. earned share of total sales', [C.SERIES_PASTEL[0], C.SERIES_PASTEL[1]], 'ov-donut-earned', C.aedShort(OV.totals.sales), 'Total sales'); },
      chart3: function () { return renderBreakdownCard('earned_share', 'product'); },
      chart4: function () { return renderBreakdownCard('earned_share', 'market'); }
    },
    unmeasured: {
      chart1: function () { return renderTrendCard(OV.trend.unmeasured_share, 'Unmeasured spend across the 8-week cycle', 'TV spend as a share of total media spend, week by week', ovPct0, OV_ACCENTS[4], 'ov-trend-unmeasured'); },
      chart2: function () { return renderDonutCard(OV.measured_split, 'How much of the budget can be measured', 'Spend with an attributed return vs. TV’s measurement gap', [C.SERIES_PASTEL[0], REALLOC_PASTEL.down], 'ov-donut-measured', C.aedShort(OV.totals.spend), 'Total spend'); },
      chart3: function () { return renderBreakdownCard('unmeasured', 'market'); },
      chart4: function () { return renderBreakdownCard('unmeasured', 'channel'); }
    }
  };

  function applyOverviewKpi(kpi) {
    if (!OV || !OV_KPIS[kpi]) return;
    ovKpi = kpi;
    var cfg = OV_KPIS[kpi];
    [1, 2, 3, 4].forEach(function (i) {
      var el = document.getElementById('ov-chart-' + i);
      if (el) el.innerHTML = cfg['chart' + i]();
    });
    document.querySelectorAll('#mount-kpis [data-kpi]').forEach(function (el) {
      el.classList.toggle('selected', el.getAttribute('data-kpi') === kpi);
    });
  }

  function initOverview() {
    if (!document.getElementById('mount-kpis') || !document.getElementById('ov-chart-1')) return;
    OV = window.__OVERVIEW_DATA__ || null;
    document.addEventListener('click', function (e) {
      var kpiEl = e.target.closest('#mount-kpis [data-kpi]');
      if (kpiEl) applyOverviewKpi(kpiEl.getAttribute('data-kpi'));
    });
  }

  // Rebuilds the same shape as window.__OVERVIEW_DATA__ (see build_site.py's
  // page_overview) from a live-filtered table set, so the KPI-driven charts
  // keep working under the top filter bar exactly like every other chart on
  // this page. "Earned share by product" and "unmeasured spend by market"
  // aren't precomputed columns -- aggregated here from fact_base's own
  // media_type/revenue_attributed tags, mirroring the Python side exactly.
  function computeOverviewData(t) {
    var spine = t.fact_market_week, eff = t.channel_efficiency, ms = t.market_scorecard,
      ps = t.product_summary, pve = t.paid_vs_earned, baseRows = t.fact_base || [];
    var tv = eff.filter(function (r) { return r.channel === 'TV'; })[0];
    var totalSpend = sum(spine, 'spend_aed'), totalSales = sum(spine, 'sales_aed');

    var weeks = weeksOf(spine);
    var byWeek = weeks.map(function (w) {
      var rows = spine.filter(function (r) { return r.week === w; });
      return {
        sales: sum(rows, 'sales_aed'), spend: sum(rows, 'spend_aed'),
        earned: sum(rows, 'earned_sales_aed'), tvSpend: sum(rows, 'tv_spend_aed')
      };
    });
    var trend = {
      sales: byWeek.map(function (r) { return r.sales; }),
      spend: byWeek.map(function (r) { return r.spend; }),
      mer: byWeek.map(function (r) { return r.spend ? r.sales / r.spend : null; }),
      earned_share: byWeek.map(function (r) { return r.sales ? r.earned / r.sales * 100 : null; }),
      unmeasured_share: byWeek.map(function (r) { return r.spend ? r.tvSpend / r.spend * 100 : null; })
    };

    var MKT_LABEL = window.Filters.MARKET_LABEL;
    function mktLabel(r) { return r.market + ' (' + MKT_LABEL[r.market] + ')'; }
    function rows(list, key, valueKey) {
      return list.map(function (r) {
        var v = r[valueKey];
        return { label: r[key], fval: r[key], value: (v === null || v === undefined || isNaN(v)) ? null : v };
      });
    }
    function marketRows(list, valueKey) {
      return list.map(function (r) { return { label: mktLabel(r), fval: r.market, value: r[valueKey] }; });
    }

    var effSales = eff.slice().sort(function (a, b) { return b.sales_aed - a.sales_aed; });
    var effSpend = eff.slice().sort(function (a, b) { return b.spend_aed - a.spend_aed; });
    var msSales = ms.slice().sort(function (a, b) { return b.sales_aed - a.sales_aed; });
    var msSpend = ms.slice().sort(function (a, b) { return b.spend_aed - a.spend_aed; });
    var psSales = ps.slice().sort(function (a, b) { return b.sales_aed - a.sales_aed; });
    var psSpend = ps.slice().sort(function (a, b) { return b.spend_aed - a.spend_aed; });
    var measurable = eff.filter(function (r) { return r.revenue_attributed && r.roas !== null; })
      .sort(function (a, b) { return b.roas - a.roas; });
    var msMer = ms.slice().sort(function (a, b) { return b.mer - a.mer; });
    var psMer = ps.filter(function (r) { return r.roas !== null && r.roas !== undefined; })
      .sort(function (a, b) { return b.roas - a.roas; });
    var msEarned = ms.slice().sort(function (a, b) { return b.earned_sales_share - a.earned_sales_share; });

    var prodMedia = {};
    baseRows.forEach(function (r) {
      var p = prodMedia[r.product] = prodMedia[r.product] || { paid: 0, earned: 0 };
      p[r.media_type === 'earned' ? 'earned' : 'paid'] += r.sales_aed || 0;
    });
    var prodEarned = Object.keys(prodMedia).map(function (p) {
      var m = prodMedia[p], total = m.paid + m.earned;
      return { label: p, fval: p, value: total > 0 ? m.earned / total * 100 : null };
    }).sort(function (a, b) { return (b.value || 0) - (a.value || 0); });

    var unmeasChannels = {};
    eff.forEach(function (r) { if (!r.revenue_attributed) unmeasChannels[r.channel] = true; });
    var mktUnmeasMap = {};
    ms.forEach(function (r) { mktUnmeasMap[r.market] = 0; });
    baseRows.forEach(function (r) {
      if (unmeasChannels[r.channel]) mktUnmeasMap[r.market] = (mktUnmeasMap[r.market] || 0) + (r.spend_aed || 0);
    });
    var mktUnmeas = ms.map(function (r) { return { label: mktLabel(r), fval: r.market, value: mktUnmeasMap[r.market] || 0 }; })
      .sort(function (a, b) { return b.value - a.value; });
    var chanUnmeas = eff.map(function (r) {
      return { label: r.channel, fval: r.channel, value: r.revenue_attributed ? 0 : (r.spend_aed || 0) };
    }).sort(function (a, b) { return b.value - a.value; });

    var breakdown = {
      sales: { channel: rows(effSales, 'channel', 'sales_aed'), market: marketRows(msSales, 'sales_aed'), product: rows(psSales, 'product', 'sales_aed') },
      spend: { channel: rows(effSpend, 'channel', 'spend_aed'), market: marketRows(msSpend, 'spend_aed'), product: rows(psSpend, 'product', 'spend_aed') },
      mer: { channel: rows(measurable, 'channel', 'roas'), market: marketRows(msMer, 'mer'), product: rows(psMer, 'product', 'roas') },
      earned_share: {
        market: msEarned.map(function (r) { return { label: mktLabel(r), fval: r.market, value: r.earned_sales_share !== null && r.earned_sales_share !== undefined ? r.earned_sales_share * 100 : null }; }),
        product: prodEarned
      },
      unmeasured: { market: mktUnmeas, channel: chanUnmeas }
    };

    var pveIdx = {};
    pve.forEach(function (r) { pveIdx[r.media_type] = r; });
    var earnedContrib = [
      { label: 'Paid', fval: 'Paid', value: pveIdx.paid ? pveIdx.paid.sales_aed : 0 },
      { label: 'Earned', fval: 'Earned', value: pveIdx.earned ? pveIdx.earned.sales_aed : 0 }
    ];
    var measuredSplit = [
      { label: 'Measured', fval: 'Measured', value: totalSpend - (tv ? tv.spend_aed : 0) },
      { label: 'Unmeasured', fval: 'Unmeasured', value: tv ? tv.spend_aed : 0 }
    ];

    return {
      weeks: weeks.map(function (w) { return 'Wk ' + w; }), trend: trend, breakdown: breakdown,
      earned_contrib: earnedContrib, measured_split: measuredSplit,
      totals: { sales: totalSales, spend: totalSpend },
      tv_share_of_spend: tv ? tv.share_of_spend : 0
    };
  }

  function overview(t, active) {
    var spine = t.fact_market_week, eff = t.channel_efficiency;
    var alertsCurrent = t.alerts_current;
    if (!spine.length || !eff.length) return; // degenerate slice -- leave the last good render in place

    var totalSpend = sum(spine, 'spend_aed'), totalSales = sum(spine, 'sales_aed');
    var tv = eff.filter(function (r) { return r.channel === 'TV'; })[0];

    // ---- KPIs (unchanged definitions -- see src/build_site.py's page_overview) --
    var weeks = weeksOf(spine);
    var byWeek = weeks.map(function (w) {
      var rows = spine.filter(function (r) { return r.week === w; });
      return {
        sales: sum(rows, 'sales_aed'), spend: sum(rows, 'spend_aed'),
        earned: sum(rows, 'earned_sales_aed'), tvSpend: sum(rows, 'tv_spend_aed')
      };
    });
    var salesTrend = byWeek.map(function (r) { return r.sales; });
    var spendTrend = byWeek.map(function (r) { return r.spend; });
    var merTrend = byWeek.map(function (r) { return r.spend ? r.sales / r.spend : null; });
    var earnedTrend = byWeek.map(function (r) { return r.sales ? r.earned / r.sales * 100 : null; });
    var tvShareTrend = byWeek.map(function (r) { return r.spend ? r.tvSpend / r.spend * 100 : null; });
    var pve = t.paid_vs_earned;
    var earnedRow = pve.filter(function (r) { return r.media_type === 'earned'; })[0];
    var earnedShare = earnedRow ? earnedRow.share_of_sales : null;

    var kpiEl = document.getElementById('mount-kpis');
    if (kpiEl && tv) {
      kpiEl.innerHTML = '<div class="kpis">' + [
        C.kpiSelect('sales', C.kpiCard({ label: 'Sales', value: C.aed(totalSales),
          delta: wow(salesTrend), vs: 'vs first half', spark: salesTrend, sparkColor: OV_ACCENTS[0] }), ovKpi === 'sales'),
        C.kpiSelect('spend', C.kpiCard({ label: 'Media spend', value: C.aed(totalSpend),
          delta: wow(spendTrend), goodUp: false, vs: 'vs first half', spark: spendTrend, sparkColor: OV_ACCENTS[1] }), ovKpi === 'spend'),
        C.kpiSelect('mer', C.kpiCard({ label: 'MER', value: (totalSales / totalSpend).toFixed(1), unit: 'x',
          delta: wow(merTrend), vs: 'vs first half', spark: merTrend, sparkColor: OV_ACCENTS[2] }), ovKpi === 'mer'),
        C.kpiSelect('earned', C.kpiCard({ label: 'Earned share of sales', value: (earnedShare * 100).toFixed(0), unit: '%',
          delta: wow(earnedTrend), vs: 'vs first half', spark: earnedTrend, sparkColor: OV_ACCENTS[3] }), ovKpi === 'earned'),
        C.kpiSelect('unmeasured', C.kpiCard({ label: 'Unmeasured spend', value: (tv.share_of_spend * 100).toFixed(0), unit: '%',
          delta: wow(tvShareTrend), goodUp: false, vs: 'vs first half', spark: tvShareTrend, sparkColor: OV_ACCENTS[4] }), ovKpi === 'unmeasured'),
        C.kpiLink('alerts.html', C.kpiCard({ label: 'Open alerts', value: String(alertsCurrent.length) }), true)
      ].join('') + '</div>';
    }

    // ---- the four charts the selected KPI explains -------------------------
    if (document.getElementById('ov-chart-1')) {
      OV = computeOverviewData(t);
      applyOverviewKpi(ovKpi);
    }
  }

  // Insights & Actions page. The KPI row is the only thing computed here --
  // everything else (write-up, trends, recommended actions) is generated on
  // demand by the AI assistant (see initAiInsights below), scoped to
  // whatever filter is active when the button is clicked. No formula-based
  // fallback text is baked in any more.
  var aiInsightsGenerated = false;
  function insights(t, active) {
    var spine = t.fact_market_week;
    if (!spine.length) return; // degenerate slice -- leave the last good render in place

    var totalSales = sum(spine, 'sales_aed'), totalSpend = sum(spine, 'spend_aed');
    var blendedMer = totalSpend ? totalSales / totalSpend : null;

    var kpiEl = document.getElementById('mount-insights-kpis');
    if (kpiEl) {
      kpiEl.innerHTML = '<div class="kpis">' +
        C.kpiCard({ label: 'Sales', value: C.aed(totalSales) }) +
        C.kpiCard({ label: 'Media spend', value: C.aed(totalSpend) }) +
        C.kpiCard({ label: 'Blended MER', value: blendedMer === null ? '—' : blendedMer.toFixed(1), unit: 'x' }) +
        '</div>';
    }

    // The filter moved since the last AI generation (if any) -- the write-up
    // on screen no longer matches what's in the KPI row above it, so clear
    // it rather than leave a stale answer looking current.
    if (aiInsightsGenerated) {
      aiInsightsGenerated = false;
      ['mount-ai-perf', 'mount-ai-actions'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.innerHTML = '';
      });
      var bodyEl = document.getElementById('mount-ai-body');
      if (bodyEl) bodyEl.style.display = 'none';
      var note = document.getElementById('ai-insights-note');
      if (note) { note.className = 'fbar-note'; note.textContent = 'Filter changed — click Generate AI insights to refresh.'; }
    }
  }

  function intFmt(v) { return (v === null || v === undefined || isNaN(v) || v === 0) ? '—' : Math.round(v).toLocaleString(); }
  function ctrFmt(v) { return (v === null || v === undefined || isNaN(v)) ? '—' : v.toFixed(2) + '%'; }
  function attributionPill(attributed) {
    return attributed ? '<span class="pill ok">Measured</span>' : '<span class="pill bad">Gap</span>';
  }
  function severityPill(sev) {
    return '<span class="pill sev-' + sev + '">' + C.esc(sev) + '</span>';
  }
  // Pastel-but-still-directional: matches src/build_site.py's REALLOC_PASTEL.
  var REALLOC_PASTEL = { down: '#F2A6A6', up: C.SERIES_PASTEL[0] };

  /* ------------------------------------------------- channel drill-down */
  // State for the Channels page's click-a-slice interaction. channelDrilldown
  // starts as window.__CHANNEL_DRILLDOWN__ (baked at build time, so it works
  // with no server too) and is replaced with a fresh aggregation of
  // t.fact_base whenever a live filter change re-runs channels() below --
  // same "static default, live replaces it" split as infRows/__INF_SCORECARD__.
  var channelDrilldown = null;
  var selectedChannel = null;

  function aggregateChannelRows(rows, dimKey) {
    var map = {};
    rows.forEach(function (r) {
      var k = r[dimKey];
      if (!map[k]) map[k] = { spend_aed: 0, sales_aed: 0, conversions: 0 };
      map[k].spend_aed += r.spend_aed || 0;
      map[k].sales_aed += r.sales_aed || 0;
      map[k].conversions += r.conversions || 0;
    });
    return Object.keys(map).map(function (k) {
      var o = map[k]; o[dimKey] = k; return o;
    }).filter(function (o) {
      return o.spend_aed > 0 || o.sales_aed > 0;
    }).sort(function (a, b) { return b.sales_aed - a.sales_aed; });
  }

  function buildChannelDrilldown(baseRows, eff, channelList) {
    var out = {};
    channelList.forEach(function (ch) {
      var sub = baseRows.filter(function (r) { return r.channel === ch; });
      var row = eff.filter(function (r) { return r.channel === ch; })[0];
      out[ch] = {
        kpis: {
          spend_aed: row ? row.spend_aed : sum(sub, 'spend_aed'),
          sales_aed: row ? row.sales_aed : sum(sub, 'sales_aed'),
          conversions: row ? row.conversions : sum(sub, 'conversions'),
          roas: (row && row.roas !== null && row.roas !== undefined) ? row.roas : null
        },
        by_product: aggregateChannelRows(sub, 'product'),
        by_market: aggregateChannelRows(sub, 'market')
      };
    });
    return out;
  }

  function renderChannelDetailKpis(k) {
    return '<div class="kpis">' + [
      C.kpiCard({ label: 'Spend', value: C.aed(k.spend_aed) }),
      C.kpiCard({ label: 'Sales', value: C.aed(k.sales_aed) }),
      C.kpiCard({ label: 'Conversions', value: Math.round(k.conversions).toLocaleString() }),
      C.kpiCard({ label: 'ROAS', value: C.xFmt(k.roas) })
    ].join('') + '</div>';
  }

  function renderChannelDetailCard(title, rows, dimKey) {
    var MKT_LABEL = window.Filters.MARKET_LABEL;
    var labels = rows.map(function (r) {
      return dimKey === 'market' ? (r.market + ' (' + MKT_LABEL[r.market] + ')') : r[dimKey];
    });
    return '<div class="card"><div class="card-head"><h3>' + title + '</h3></div>' +
      C.legend([['Spend', C.SERIES_PASTEL[0]], ['Sales', C.SERIES_PASTEL[1]]], { symbol: 'dot' }) +
      C.groupedBarH(labels, [
        ['Spend', rows.map(function (r) { return r.spend_aed; }), C.SERIES_PASTEL[0]],
        ['Sales', rows.map(function (r) { return r.sales_aed; }), C.SERIES_PASTEL[1]]
      ], { vFmt: C.aedShort, labelSeries: 1, chartId: 'ch-detail-' + dimKey }) + '</div>';
  }

  function applyChannelSelection(ch) {
    if (!channelDrilldown || !channelDrilldown[ch]) return;
    selectedChannel = ch;
    var dd = channelDrilldown[ch];
    var kpiEl = document.getElementById('mount-channel-detail-kpis');
    if (kpiEl) kpiEl.innerHTML = renderChannelDetailKpis(dd.kpis);
    var prodEl = document.getElementById('mount-channel-detail-product');
    if (prodEl) prodEl.innerHTML = renderChannelDetailCard('By product', dd.by_product, 'product');
    var mktEl = document.getElementById('mount-channel-detail-market');
    if (mktEl) mktEl.innerHTML = renderChannelDetailCard('By market', dd.by_market, 'market');
    document.querySelectorAll('.pie-slice, .pie-legend-item').forEach(function (el) {
      el.classList.toggle('selected', el.getAttribute('data-select-val') === ch);
    });
  }

  function initChannelDrilldown() {
    if (!document.getElementById('mount-channel-detail-kpis')) return;
    channelDrilldown = window.__CHANNEL_DRILLDOWN__ || {};
    selectedChannel = window.__CHANNEL_DEFAULT__ || Object.keys(channelDrilldown)[0] || null;
    document.addEventListener('click', function (e) {
      var el = e.target.closest('[data-select-dim="channel"]');
      if (!el) return;
      applyChannelSelection(el.getAttribute('data-select-val'));
    });
  }

  function channels(t, active) {
    var eff = t.channel_efficiency;
    if (!eff.length) return;

    var kpiEl = document.getElementById('mount-channel-kpis');
    if (kpiEl) {
      var totalSpend = sum(eff, 'spend_aed'), totalSales = sum(eff, 'sales_aed'), totalConv = sum(eff, 'conversions');
      var blendedMer = totalSpend ? totalSales / totalSpend : null;
      kpiEl.innerHTML = '<div class="kpis">' + [
        C.kpiCard({ label: 'Total spend', value: C.aed(totalSpend) }),
        C.kpiCard({ label: 'Total sales', value: C.aed(totalSales) }),
        C.kpiCard({ label: 'Total conversions', value: Math.round(totalConv).toLocaleString() }),
        C.kpiCard({ label: 'Blended MER', value: blendedMer === null ? '—' : blendedMer.toFixed(1), unit: 'x' })
      ].join('') + '</div>';
    }

    var meas = eff.filter(function (r) { return r.revenue_attributed && r.roas !== null; });
    var pieSrc = meas.slice().sort(function (a, b) { return b.sales_aed - a.sales_aed; });
    var defaultChannel = pieSrc.length ? pieSrc[0].channel : null;

    var effEl = document.getElementById('mount-eff-table');
    if (effEl) {
      var econ = eff.slice().sort(function (a, b) { return b.spend_aed - a.spend_aed; }).map(function (r) {
        var c = Object.assign({}, r);
        c.ctr_pct = r.impressions > 0 ? r.clicks / r.impressions * 100 : null;
        return c;
      });

      var html =
        '<div class="card"><div class="card-head"><h3>Measured return by channel</h3>' +
        '<div class="card-sub">Each slice is a channel’s share of measured sales — TV, PR and ' +
        'Website aren’t sliced here, a measurement gap rather than a zero.</div></div>' +
        C.pieChart(pieSrc.map(function (r) { return r.channel; }), pieSrc.map(function (r) { return r.sales_aed; }),
          { vFmt: C.aedShort, chartId: 'ch-roas', selectDim: 'channel', selected: selectedChannel || defaultChannel,
            subs: pieSrc.map(function (r) { return 'ROAS ' + r.roas.toFixed(2) + 'x'; }) }) +
        C.tableView(econ, [
          { key: 'channel', label: 'channel' }, { key: 'media_type', label: 'media type' },
          { key: 'spend_aed', label: 'spend aed', fmt: C.aedShort },
          { key: 'share_of_spend', label: 'share of spend', fmt: function (v) { return C.pct(v, 0); } },
          { key: 'impressions', label: 'impressions', fmt: intFmt }, { key: 'clicks', label: 'clicks', fmt: intFmt },
          { key: 'ctr_pct', label: 'ctr', fmt: ctrFmt }, { key: 'conversions', label: 'conversions', fmt: intFmt },
          { key: 'sales_aed', label: 'sales aed', fmt: C.aedShort }, { key: 'roas', label: 'roas', fmt: C.xFmt },
          { key: 'roi_gross_margin', label: 'roi gross margin', fmt: C.xFmt },
          { key: 'revenue_attributed', label: 'attribution', fmt: attributionPill }
        ], 'View channel economics') + '</div>';
      effEl.innerHTML = html;
    }

    if (t.fact_base && t.fact_base.length && pieSrc.length) {
      var measChannels = pieSrc.map(function (r) { return r.channel; });
      channelDrilldown = buildChannelDrilldown(t.fact_base, eff, measChannels);
      if (!selectedChannel || measChannels.indexOf(selectedChannel) === -1) {
        selectedChannel = defaultChannel;
      }
      applyChannelSelection(selectedChannel);
    }
  }

  function portfolio(t) {
    var ms = t.market_scorecard, ps = t.product_summary, spine = t.fact_market_week, baseRows = t.fact_base || [];
    if (!ms.length || !ps.length) return;
    var MKT_LABEL = window.Filters.MARKET_LABEL;
    function mktLabel(code) { return code + ' (' + MKT_LABEL[code] + ')'; }

    var kpiEl = document.getElementById('mount-portfolio-kpis');
    if (kpiEl && spine && spine.length) {
      var totalConv = sum(spine, 'conversions'), totalSpend = sum(spine, 'spend_aed');
      var cpa = totalConv ? totalSpend / totalConv : null;
      kpiEl.innerHTML = '<div class="kpis">' + [
        C.kpiCard({ label: 'Conversions', value: Math.round(totalConv).toLocaleString() }),
        C.kpiCard({ label: 'CPA', value: cpa === null ? '—' : C.aed(cpa, 0) }),
        C.kpiCard({ label: 'Products', value: String(ps.length) }),
        C.kpiCard({ label: 'Markets', value: String(ms.length) })
      ].join('') + '</div>';
    }

    // ---- weekly sales across markets + product-by-market split ------------
    var weekWkEl = document.getElementById('mount-sales-week-market');
    var prodMktEl = document.getElementById('mount-sales-product-market');
    if ((weekWkEl || prodMktEl) && spine && spine.length) {
      var weeks = weeksOf(spine);
      var byMarketWeek = {};
      spine.forEach(function (r) {
        (byMarketWeek[r.market] = byMarketWeek[r.market] || {})[r.week] = (byMarketWeek[r.market][r.week] || 0) + (r.sales_aed || 0);
      });
      var marketOrder = Object.keys(byMarketWeek).sort(function (a, b) {
        return sum(spine.filter(function (r) { return r.market === b; }), 'sales_aed') -
               sum(spine.filter(function (r) { return r.market === a; }), 'sales_aed');
      });
      var marketColors = {};
      marketOrder.forEach(function (mk, i) { marketColors[mk] = C.SERIES_PASTEL[i % C.SERIES_PASTEL.length]; });
      var marketLegend = C.legend(marketOrder.map(function (mk) { return [mktLabel(mk), marketColors[mk], mk]; }), { filterDim: 'market' });

      if (weekWkEl) {
        var wkLabels = weeks.map(function (w) { return 'Wk ' + w; });
        var salesByMarket = marketOrder.map(function (mk) {
          return { label: mktLabel(mk), filterVal: mk, color: marketColors[mk],
            values: weeks.map(function (w) { return byMarketWeek[mk][w] || 0; }) };
        });
        weekWkEl.innerHTML =
          '<div class="card"><div class="card-head"><h3>Sales by week across markets</h3>' +
          '<div class="card-sub">Click a line, a point, or the legend to filter</div></div>' +
          marketLegend +
          C.lineChart(wkLabels, salesByMarket, { yFmt: C.aedShort, hoverFmt: C.aed, seriesFilterDim: 'market', chartId: 'pf-sales-week' }) +
          C.tableView(weeks.map(function (w) {
            var row = { week: w };
            marketOrder.forEach(function (mk) { row[mk] = byMarketWeek[mk][w] || 0; });
            return row;
          }), [{ key: 'week', label: 'week' }].concat(marketOrder.map(function (mk) { return { key: mk, label: mk, fmt: C.aedShort }; }))) +
          '</div>';
      }

      if (prodMktEl && baseRows.length) {
        var productsOrder = ps.slice().sort(function (a, b) { return b.sales_aed - a.sales_aed; }).map(function (r) { return r.product; });
        var byProductMarket = {};
        baseRows.forEach(function (r) {
          var p = byProductMarket[r.product] = byProductMarket[r.product] || {};
          p[r.market] = (p[r.market] || 0) + (r.sales_aed || 0);
        });
        var productByMarket = marketOrder.map(function (mk) {
          return [mktLabel(mk), productsOrder.map(function (p) { return (byProductMarket[p] && byProductMarket[p][mk]) || 0; }), marketColors[mk]];
        });
        prodMktEl.innerHTML =
          '<div class="card"><div class="card-head"><h3>Sales by product, stacked by market</h3>' +
          '<div class="card-sub">Each segment is a market’s contribution to that product’s sales — ' +
          'click the legend to filter</div></div>' +
          marketLegend +
          C.stackedColumns(productsOrder, productByMarket, { vFmt: C.aedShort, chartId: 'pf-sales-product' }) +
          C.tableView(productsOrder.map(function (p) {
            var row = { product: p };
            marketOrder.forEach(function (mk) { row[mk] = (byProductMarket[p] && byProductMarket[p][mk]) || 0; });
            return row;
          }), [{ key: 'product', label: 'product' }].concat(marketOrder.map(function (mk) { return { key: mk, label: mk, fmt: C.aedShort }; }))) +
          '</div>';
      }
    }


    var psSorted = ps.slice().sort(function (a, b) { return b.sales_aed - a.sales_aed; });
    var prodEl = document.getElementById('mount-product-table');
    if (prodEl) {
      prodEl.innerHTML = C.table(psSorted, [
        { key: 'product', label: 'product' }, { key: 'spend_aed', label: 'spend aed', fmt: C.aedShort },
        { key: 'sales_aed', label: 'sales aed', fmt: C.aedShort },
        { key: 'conversions', label: 'conversions', fmt: function (v) { return Math.round(v).toLocaleString(); } },
        { key: 'roas', label: 'roas', fmt: C.xFmt }, { key: 'aov_aed', label: 'aov aed', fmt: function (v) { return Math.round(v).toLocaleString(); } },
        { key: 'share_of_spend', label: 'share of spend', fmt: function (v) { return C.pct(v, 1); } },
        { key: 'share_of_sales', label: 'share of sales', fmt: function (v) { return C.pct(v, 1); } },
        { key: 'support_index', label: 'support index', fmt: function (v) { return v.toFixed(2); } }
      ], null, { sortable: true });
      if (window.enhanceSortableTables) window.enhanceSortableTables(prodEl);
    }
  }

  function median(vals) {
    var s = vals.slice().sort(function (a, b) { return a - b; });
    var n = s.length;
    if (!n) return null;
    return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
  }

  /* --------------------------------------------------- influencer bar chart */
  // Metric the Y axis is currently showing, and the last dataset drawn (baked
  // window.__INF_SCORECARD__ until a live filter change replaces it) -- both
  // module-scoped so the dropdown and the live re-render share one source of
  // truth regardless of which one fires next.
  var INF_METRICS = {
    roas: { label: 'ROAS', fmt: function (v) { return v.toFixed(1); } },
    cpa_aed: { label: 'CPA (AED)', fmt: function (v) { return Math.round(v).toLocaleString(); } },
    spend_aed: { label: 'Spend (AED)', fmt: C.aedShort },
    engagement_rate: { label: 'Engagement rate (%)', fmt: function (v) { return v.toFixed(1); } },
    followers: { label: 'Followers', fmt: function (v) { return Math.round(v).toLocaleString(); } }
  };
  var INF_GRADE_COLORS = { good: '#8FD9AE', mid: '#F2D97A', bad: '#F2A6A6' };
  var infMetric = 'roas';
  var infRows = null;

  function infNumber(name) {
    var parts = String(name).split('_');
    return parts[parts.length - 1];
  }

  function percentile(sortedVals, p) {
    if (!sortedVals.length) return 0;
    var idx = p * (sortedVals.length - 1);
    var lo = Math.floor(idx), hi = Math.min(lo + 1, sortedVals.length - 1);
    return sortedVals[lo] + (sortedVals[hi] - sortedVals[lo]) * (idx - lo);
  }

  function gradeColors(values) {
    // Pastel green at/above the 80th percentile of THIS metric's own
    // values, pastel red below the 20th, pastel yellow between -- a band,
    // not a fixed threshold, so it re-grades sensibly for whichever metric
    // is currently on the axis.
    var ranked = values.slice().sort(function (a, b) { return a - b; });
    var p20 = percentile(ranked, 0.2), p80 = percentile(ranked, 0.8);
    return values.map(function (v) {
      return v >= p80 ? INF_GRADE_COLORS.good : v < p20 ? INF_GRADE_COLORS.bad : INF_GRADE_COLORS.mid;
    });
  }

  function drawInfBar(rows) {
    var mount = document.getElementById('inf-bar-chart');
    if (!mount || !rows || !rows.length) return;
    var m = INF_METRICS[infMetric] || INF_METRICS.roas;
    var sorted = rows.slice().sort(function (a, b) {
      return (b[infMetric] || 0) - (a[infMetric] || 0);
    });
    var values = sorted.map(function (r) { return r[infMetric] || 0; });
    var labels = sorted.map(function (r) { return infNumber(r.influencer); });
    var titles = sorted.map(function (r) { return 'Influencer ' + infNumber(r.influencer) + ' · ' + r.market; });
    var bodies = sorted.map(function (r) {
      return '<ul class="tip-list">' +
        '<li>Followers: ' + Math.round(r.followers).toLocaleString() + '</li>' +
        '<li>Engagement: ' + r.engagement_rate.toFixed(1) + '%</li>' +
        '<li>Spend: ' + C.aed(r.spend_aed) + '</li>' +
        '<li>CPA: ' + C.aed(r.cpa_aed, 0) + '</li>' +
        '<li>ROAS: ' + r.roas.toFixed(2) + 'x</li>' +
        '</ul>';
    });
    mount.innerHTML = C.barChartGraded(labels, values, gradeColors(values), titles, bodies,
      { vFmt: m.fmt, chartId: 'inf-bar' });
  }

  function initInfBarChart() {
    var tabs = document.getElementById('inf-metric-tabs');
    if (!tabs) return;
    infRows = window.__INF_SCORECARD__ || [];
    tabs.querySelectorAll('.tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (infMetric === btn.getAttribute('data-metric')) return;
        infMetric = btn.getAttribute('data-metric');
        tabs.querySelectorAll('.tab').forEach(function (b) { b.classList.toggle('active', b === btn); });
        drawInfBar(infRows);
      });
    });
  }

  function influencers(t) {
    var sc = t.influencer_scorecard;
    if (!sc.length) return;
    var medCpa = median(sc.map(function (r) { return r.cpa_aed; }));
    var medRoas = median(sc.map(function (r) { return r.roas; }));
    var bestMargin = Math.max.apply(null, sc.map(function (r) { return r.roas * GROSS_MARGIN; }));

    var kpiEl = document.getElementById('mount-inf-kpis');
    if (kpiEl) {
      kpiEl.innerHTML = '<div class="kpis">' + [
        C.kpiCard({ label: 'Influencers', value: String(sc.length) }),
        C.kpiCard({ label: 'Total fees', value: C.aed(sum(sc, 'spend_aed')) }),
        C.kpiCard({ label: 'Median CPA', value: C.aed(medCpa, 0) }),
        C.kpiCard({ label: 'Median ROAS', value: medRoas.toFixed(2) + 'x' }),
        C.kpiCard({ label: 'Best on margin', value: bestMargin.toFixed(2) + 'x' })
      ].join('') + '</div>';
    }

    var s = sc.slice().sort(function (a, b) { return a.cpa_aed - b.cpa_aed; });

    infRows = sc;
    drawInfBar(infRows);

    var tableEl = document.getElementById('mount-inf-table');
    if (tableEl) {
      tableEl.innerHTML = C.table(s, [
        { key: 'influencer', label: 'influencer' }, { key: 'market', label: 'market' },
        { key: 'followers', label: 'followers', fmt: function (v) { return Math.round(v).toLocaleString(); } },
        { key: 'engagement_rate', label: 'engagement rate', fmt: function (v) { return v.toFixed(2) + '%'; } },
        { key: 'er_vs_roster', label: 'er vs roster', fmt: function (v) { return (v >= 0 ? '+' : '') + Math.round(v * 100) + '%'; } },
        { key: 'spend_aed', label: 'spend aed', fmt: C.aedShort },
        { key: 'cpa_aed', label: 'cpa aed', fmt: function (v) { return Math.round(v).toLocaleString(); } },
        { key: 'roas', label: 'roas', fmt: C.xFmt }, { key: 'flag', label: 'flag', fmt: flagPill },
        { key: 'recommended_action', label: 'recommended action' }
      ], null, { sortable: true });
      if (window.enhanceSortableTables) window.enhanceSortableTables(tableEl);
    }
  }

  function brand(t) {
    var ms = t.market_scorecard, spine = t.fact_market_week;
    if (!ms.length || !spine.length) return;
    var MKT_LABEL = window.Filters.MARKET_LABEL;
    function mktLabel(r) { return r.market + ' (' + MKT_LABEL[r.market] + ')'; }

    var kpiEl = document.getElementById('mount-brand-kpis');
    if (kpiEl) {
      kpiEl.innerHTML = '<div class="kpis">' + [
        C.kpiCard({ label: 'Brand awareness score', value: avg(spine.map(function (r) { return r.brand_awareness; })).toFixed(1) }),
        C.kpiCard({ label: 'Purchase intent score', value: avg(spine.map(function (r) { return r.purchase_intent; })).toFixed(1) }),
        C.kpiCard({ label: 'Sentiment score', value: avg(spine.map(function (r) { return r.sentiment; })).toFixed(2) }),
        C.kpiCard({ label: 'PR share of voice', value: avg(spine.map(function (r) { return r.share_of_voice; })).toFixed(1) }),
        C.kpiCard({ label: 'Competitor SOV', value: avg(spine.map(function (r) { return r.competitor_sov; })).toFixed(1) })
      ].join('') + '</div>';
    }

    var weeklyEl = document.getElementById('mount-brand-weekly');
    if (weeklyEl) {
      var ws = weeksOf(spine);
      var byWeek = ws.map(function (w) {
        var rows = spine.filter(function (r) { return r.week === w; });
        return {
          week: w, awareness: avg(rows.map(function (r) { return r.brand_awareness; })),
          intent: avg(rows.map(function (r) { return r.purchase_intent; }))
        };
      });
      var wkLabels = byWeek.map(function (r) { return 'Wk ' + r.week; });
      weeklyEl.innerHTML =
        '<div class="card"><div class="card-head"><h3>Brand awareness &amp; purchase intent over week</h3>' +
        '<div class="card-sub">Group average, indicative index</div></div>' +
        C.legend([['Awareness', C.SERIES_PASTEL[0]], ['Purchase intent', C.SERIES_PASTEL[1]]]) +
        C.lineChart(wkLabels, [
          { label: 'Awareness', values: byWeek.map(function (r) { return r.awareness; }), color: C.SERIES_PASTEL[0] },
          { label: 'Purchase intent', values: byWeek.map(function (r) { return r.intent; }), color: C.SERIES_PASTEL[1] }
        ], { yFmt: function (v) { return v.toFixed(0); }, chartId: 'br-wk' }) + '</div>';
    }

    var sentEl = document.getElementById('mount-brand-sentiment');
    if (sentEl) {
      var msSent = ms.slice().sort(function (a, b) { return b.sentiment - a.sentiment; });
      sentEl.innerHTML =
        '<div class="card"><div class="card-head"><h3>Sentiment by market</h3>' +
        '<div class="card-sub">Averaged across the weeks in scope</div></div>' +
        C.lollipopChart(msSent.map(mktLabel), msSent.map(function (r) { return r.sentiment; }),
          { colors: msSent.map(function () { return C.SERIES_PASTEL[2]; }), vFmt: function (v) { return v.toFixed(2); },
            filterDim: 'market', filterVals: msSent.map(function (r) { return r.market; }), chartId: 'br-sent-mkt' }) + '</div>';
    }

    var sovEl = document.getElementById('mount-brand-sov');
    if (sovEl) {
      var msSov = ms.slice().sort(function (a, b) { return b.share_of_voice - a.share_of_voice; });
      var sovLabels = msSov.map(mktLabel);
      sovEl.innerHTML =
        '<div class="card"><div class="card-head"><h3>Samsung PR SOV vs competitor SOV</h3>' +
        '<div class="card-sub">Percentage points, by market</div></div>' +
        C.legend([['Samsung', C.SERIES_PASTEL[0]], ['Competitor', C.SERIES_PASTEL[3]]]) +
        C.groupedBarH(sovLabels, [
          ['Samsung', msSov.map(function (r) { return r.share_of_voice; }), C.SERIES_PASTEL[0]],
          ['Competitor', msSov.map(function (r) { return r.competitor_sov; }), C.SERIES_PASTEL[3]]
        ], { vFmt: function (v) { return v.toFixed(1); }, labelSeries: 0, chartId: 'br-sov-grp' }) +
        C.tableView(msSov, [
          { key: 'market', label: 'market' },
          { key: 'share_of_voice', label: 'share of voice', fmt: function (v) { return v.toFixed(1); } },
          { key: 'competitor_sov', label: 'competitor sov', fmt: function (v) { return v.toFixed(1); } },
          { key: 'sov_gap', label: 'sov gap', fmt: function (v) { return (v >= 0 ? '+' : '') + v.toFixed(1); } }
        ]) + '</div>';
    }

    var awareMktEl = document.getElementById('mount-brand-awareness-market');
    if (awareMktEl) {
      var msAware = ms.slice().sort(function (a, b) { return b.brand_awareness - a.brand_awareness; });
      awareMktEl.innerHTML =
        '<div class="card"><div class="card-head"><h3>Brand awareness by market</h3>' +
        '<div class="card-sub">Averaged across the weeks in scope</div></div>' +
        C.barChartH(msAware.map(mktLabel), msAware.map(function (r) { return r.brand_awareness; }),
          { colors: msAware.map(function () { return C.SERIES_PASTEL[0]; }), vFmt: function (v) { return v.toFixed(1); },
            filterDim: 'market', filterVals: msAware.map(function (r) { return r.market; }), chartId: 'br-aware-mkt' }) + '</div>';
    }
  }

  // Vivid for the alert list itself (small text/border needs the contrast);
  // pastel twin for the standalone "Alerts fired per week" chart, matching
  // src/build_site.py's sev_color/sev_color_pastel split.
  var SEV_COLOR = { critical: '#DC2626', high: '#EA580C', medium: '#EAB308' };
  var SEV_COLOR_PASTEL = { critical: '#F2A6A6', high: '#F2AD5C', medium: '#F2D98A' };
  var SEV_GLYPH = { critical: '●', high: '▲', medium: '■' };

  function applyRowFilter(rows, active) {
    // Row-filter on whichever active dims the table actually has columns for.
    // alerts/alerts_current are GLOBAL_ONLY server-side (the rule engine
    // always runs on the full panel) -- this only narrows which rows are
    // SHOWN, not which alerts fired.
    return rows.filter(function (r) {
      return ['market', 'week'].every(function (dim) {
        if (!active[dim] || !active[dim].length) return true;
        if (!(dim in r)) return true;
        return active[dim].indexOf(r[dim]) >= 0;
      });
    });
  }

  // Set by the sensitivity control below once the manager clicks Apply; takes
  // priority over whatever /api/tables last returned for alerts/alerts_current
  // so a custom sensitivity survives a later week/market filter change. Reset
  // to null on every real page load (this is a fresh script context per page,
  // not an SPA), which is exactly the "back to default" behaviour wanted.
  var sensOverride = null;

  function earlyWarning(t, active) {
    var alerts = (sensOverride && sensOverride.alerts) || t.alerts;
    var current = (sensOverride && sensOverride.alerts_current) || t.alerts_current;
    if (!alerts) return;
    var shown = applyRowFilter(alerts, active);
    var shownCurrent = applyRowFilter(current, active);
    var counts = {};
    shownCurrent.forEach(function (r) { counts[r.severity] = (counts[r.severity] || 0) + 1; });

    var kpiEl = document.getElementById('mount-ew-kpis');
    if (kpiEl) {
      kpiEl.innerHTML = '<div class="kpis">' + [
        C.kpiCard({ label: 'Open now', value: String(shownCurrent.length) }),
        C.kpiCard({ label: 'Critical', value: String(counts.critical || 0) }),
        C.kpiCard({ label: 'High', value: String(counts.high || 0) }),
        C.kpiCard({ label: 'Medium', value: String(counts.medium || 0) }),
        C.kpiCard({ label: 'Fired across 8 weeks', value: String(alerts.length) })
      ].join('') + '</div>';
    }

    var openEl = document.getElementById('mount-ew-open');
    if (openEl) {
      if (!shownCurrent.length) {
        openEl.innerHTML = '<div class="card">No alerts open in this slice.</div>';
      } else {
        var groups = {}, order = [];
        shownCurrent.forEach(function (r) {
          var key = [r.rule_id, r.rule, r.severity, r.category, r.owner, r.action].join('|');
          if (!groups[key]) { groups[key] = { r: r, rows: [] }; order.push(key); }
          groups[key].rows.push(r);
        });
        openEl.innerHTML = order.map(function (key) {
          var g = groups[key], r = g.r, c = SEV_COLOR[r.severity] || '#8a8a86';
          var lines = g.rows.map(function (row) {
            var wk = (row.week === null || row.week === undefined) ? '' : ' · week ' + row.week;
            return '<div style="margin-top:4px"><b>' + C.esc(row.entity) + '</b>' + wk + ' — ' + C.esc(row.detail) + '</div>';
          }).join('');
          var scope = g.rows.length > 1 ? '<span class="alert-scope">' + g.rows.length + ' affected</span>' : '';
          return '<details class="alert" style="border-left-color:' + c + '">' +
            '<summary class="alert-summary">' +
            '<span class="alert-sev" style="color:' + c + '">' + (SEV_GLYPH[r.severity] || '•') + ' ' + C.esc(r.severity) + '</span>' +
            '<span class="alert-title">' + C.esc(r.rule) + '</span>' + scope + '</summary>' +
            '<div class="alert-body">' +
            '<div class="alert-meta">' + C.esc(r.category) + ' · ' + C.esc(r.rule_id) + '</div>' +
            '<div class="alert-detail">' + lines + '</div>' +
            '<div class="alert-foot"><b>Owner:</b> ' + C.esc(r.owner) + '<br><b>Action:</b> ' + C.esc(r.action) + '</div></div></details>';
        }).join('');
      }
    }

    var histEl = document.getElementById('mount-ew-history');
    if (histEl) {
      var dated = shown.filter(function (r) { return r.week !== null && r.week !== undefined; });
      if (!dated.length) {
        histEl.innerHTML = '';
      } else {
        var byWeekSev = {};
        dated.forEach(function (r) { (byWeekSev[r.week] = byWeekSev[r.week] || {})[r.severity] = (byWeekSev[r.week][r.severity] || 0) + 1; });
        var weeks8 = [1, 2, 3, 4, 5, 6, 7, 8];
        var wkLabels = weeks8.map(function (w) { return 'Wk ' + w; });
        var series = [
          ['Critical', weeks8.map(function (w) { return (byWeekSev[w] || {}).critical || 0; }), SEV_COLOR_PASTEL.critical],
          ['High', weeks8.map(function (w) { return (byWeekSev[w] || {}).high || 0; }), SEV_COLOR_PASTEL.high],
          ['Medium', weeks8.map(function (w) { return (byWeekSev[w] || {}).medium || 0; }), SEV_COLOR_PASTEL.medium]
        ];
        histEl.innerHTML = '<h2>What the rules would have caught</h2>' +
          '<div class="card"><div class="card-head"><h3>Alerts fired per week</h3><div class="card-sub">Back-tested across all 8 weeks</div></div>' +
          C.legend([['Critical', SEV_COLOR_PASTEL.critical], ['High', SEV_COLOR_PASTEL.high], ['Medium', SEV_COLOR_PASTEL.medium]]) +
          C.stackedColumns(wkLabels, series, { chartId: 'al-hist' }) +
          C.tableView(dated.reduce(function (acc, r) {
            var found = acc.filter(function (a) { return a.week === r.week && a.severity === r.severity; })[0];
            if (found) found.alerts++; else acc.push({ week: r.week, severity: r.severity, alerts: 1 });
            return acc;
          }, []), [{ key: 'week', label: 'week' },
            { key: 'severity', label: 'severity', fmt: severityPill },
            { key: 'alerts', label: 'alerts' }]) + '</div>';
      }
    }

    // Catalogue always reflects the full back-test (not the week/market row
    // filter above), same as build_site.py's static render -- it answers "how
    // often has this rule fired overall", not "in the current view".
    var catEl = document.getElementById('mount-ew-catalogue');
    if (catEl) {
      var groups = {};
      alerts.forEach(function (r) {
        var key = [r.rule_id, r.rule, r.category, r.severity, r.owner].join('|');
        if (!groups[key]) groups[key] = { rule_id: r.rule_id, rule: r.rule, category: r.category, severity: r.severity, owner: r.owner, times_fired: 0 };
        groups[key].times_fired++;
      });
      var catRows = Object.keys(groups).map(function (k) { return groups[k]; });
      catRows.sort(function (a, b) {
        if (a.severity !== b.severity) return a.severity < b.severity ? -1 : 1;
        return b.times_fired - a.times_fired;
      });
      catEl.innerHTML = C.table(catRows, [
        { key: 'rule_id', label: 'rule id' }, { key: 'rule', label: 'rule' },
        { key: 'category', label: 'category' },
        { key: 'severity', label: 'severity', fmt: severityPill },
        { key: 'owner', label: 'owner' },
        { key: 'times_fired', label: 'times fired', fmt: function (v) { return v.toLocaleString(); } }
      ]);
    }
  }

  function applySensitivity(gapPct) {
    var note = document.getElementById('sens-note');
    var btn = document.getElementById('sens-apply');
    if (btn) btn.disabled = true;
    fetch('/api/alerts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ min_relative_gap: gapPct / 100 })
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (j) {
      if (j.error) throw new Error(j.error);
      sensOverride = { alerts: j.alerts, alerts_current: j.alerts_current };
      if (note) { note.className = 'fbar-note'; note.textContent = 'Applied — ' + gapPct + '% minimum gap.'; }
      earlyWarning({}, window.Filters.STATE);
    }).catch(function () {
      if (note) { note.className = 'fbar-note fbar-error'; note.textContent = "Couldn't reach the live server — sensitivity not applied."; }
    }).finally(function () {
      if (btn) btn.disabled = false;
    });
  }

  function initSensitivity() {
    var mount = document.getElementById('mount-ew-sensitivity');
    if (!mount || !window.Filters || !window.Filters.onLiveKnown) return;
    var slider = document.getElementById('sens-slider');
    var valueEl = document.getElementById('sens-value');
    var btn = document.getElementById('sens-apply');
    var note = document.getElementById('sens-note');
    if (slider && valueEl) {
      slider.addEventListener('input', function () { valueEl.textContent = slider.value + '%'; });
    }
    window.Filters.onLiveKnown(function (isLive) {
      if (!isLive) {
        if (slider) slider.disabled = true;
        if (btn) btn.disabled = true;
        if (note) { note.className = 'fbar-note'; note.innerHTML = '<span class="fbar-offline">Offline — run <code>python src/serve.py</code> to adjust sensitivity.</span>'; }
        return;
      }
      if (btn) btn.addEventListener('click', function () { applySensitivity(parseInt(slider.value, 10)); });
    });
  }

  // "Generate AI insights" button on the Insights & Actions page. Fills two
  // plain bullet lists (Insights / Recommended actions) inside #mount-ai-body
  // from /api/insights, scoped to window.Filters.STATE -- the same filter
  // the KPI row above is already showing. This is the ONLY source of the
  // write-up now; there is no formula-based fallback text to leave alone, so
  // a filter change (see insights() above) hides the body and clears these
  // mounts rather than leaving them stale.
  function bulletList(items) {
    return '<ul class="bullets">' + items.map(function (b) { return '<li>' + C.esc(b) + '</li>'; }).join('') + '</ul>';
  }
  function applyAiInsights(j) {
    var bodyEl = document.getElementById('mount-ai-body');
    var perfEl = document.getElementById('mount-ai-perf');
    if (perfEl && j.insights && j.insights.length) perfEl.innerHTML = bulletList(j.insights);
    var actionsEl = document.getElementById('mount-ai-actions');
    if (actionsEl && j.actions && j.actions.length) actionsEl.innerHTML = bulletList(j.actions);
    if (bodyEl) bodyEl.style.display = '';
    aiInsightsGenerated = true;
  }

  function initAiInsights() {
    var mount = document.getElementById('mount-ai-insights');
    if (!mount || !window.Filters || !window.Filters.onLiveKnown) return;
    var btn = document.getElementById('ai-insights-btn');
    var note = document.getElementById('ai-insights-note');
    window.Filters.onLiveKnown(function (isLive) {
      if (!isLive) {
        if (btn) btn.disabled = true;
        if (note) {
          note.className = 'fbar-note';
          note.innerHTML = '<span class="fbar-offline">Offline — run <code>python src/serve.py</code> ' +
            'with a GEMINI_API_KEY set to generate AI insights.</span>';
        }
        return;
      }
      if (btn) btn.addEventListener('click', function () {
        btn.disabled = true;
        if (note) { note.className = 'fbar-note'; note.textContent = 'Generating…'; }
        fetch('/api/insights', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(window.Filters.STATE)
        }).then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        }).then(function (j) {
          if (!j.live) throw new Error(j.error || 'No API key set on the server.');
          if (j.error) throw new Error(j.error);
          applyAiInsights(j);
          if (note) { note.className = 'fbar-note'; note.textContent = 'AI-generated from the current filter. Regenerate any time.'; }
        }).catch(function (err) {
          if (note) { note.className = 'fbar-note fbar-error'; note.textContent = err.message || "Couldn't generate AI insights."; }
        }).finally(function () {
          btn.disabled = false;
        });
      });
    });
  }

  document.addEventListener('DOMContentLoaded', initSensitivity);
  document.addEventListener('DOMContentLoaded', initInfBarChart);
  document.addEventListener('DOMContentLoaded', initChannelDrilldown);
  document.addEventListener('DOMContentLoaded', initOverview);
  document.addEventListener('DOMContentLoaded', initAiInsights);

  window.Filters.Pages.overview = overview;
  window.Filters.Pages.channels = channels;
  window.Filters.Pages.portfolio = portfolio;
  window.Filters.Pages.influencers = influencers;
  window.Filters.Pages.brand = brand;
  window.Filters.Pages.insights = insights;
  window.Filters.Pages.alerts = earlyWarning;
})();
