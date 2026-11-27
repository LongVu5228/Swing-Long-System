// Shared by screener.html and chart.html: data fetch, timeframes, chart construction (candles + SMA10/20 + volume).
const TF = {            // label -> bars shown on reset (daily unless weekly); 1M is used by the armed panel minis only
  "1M": {bars: 21, weekly: false, panelOnly: true}, "2M": {bars: 42, weekly: false, panelOnly: true}, "3M": {bars: 63, weekly: false}, "6M": {bars: 126, weekly: false}, "1Y": {bars: 252, weekly: false},
  "5Y D": {bars: 1260, weekly: false}, "5Y W": {bars: 260, weekly: true},
};
const COL = {up: "#089981", down: "#f23645", sma10: "#2962ff", sma20: "#ff9800", r1: "#e91e63", flag: "#7e57c2", earn: "#9c27b0"};
const PAT_COLOR = {"Green HTF": "#089981", "Perfect HTF": "#00897b", "Big Green Flag": "#2e7d32", "Big Perfect Flag": "#1b5e20",
                   "Red HTF": "#f23645", "Big Red Flag": "#b71c1c"};
const CHAN = ("BroadcastChannel" in window) ? new BroadcastChannel("htf-screener") : null;

async function getJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.json();
}
function postJSON(url, body) {
  return getJSON(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
}
const fmt = {
  px: v => v == null ? "–" : (v >= 100 ? v.toFixed(2) : v >= 1 ? v.toFixed(2) : v.toFixed(4)),
  pct: (v, d = 1) => v == null ? "–" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d) + "%",
  cap: m => m == null ? "–" : m >= 1000 ? "$" + (m / 1000).toFixed(1) + "B" : "$" + Math.round(m) + "M",
  usd: v => v == null ? "–" : "$" + Math.round(v).toLocaleString(),
};

function ymd(t) {      // chart time ("2026-03-20" string or {year, month, day}) -> "2026-03-20"
  if (typeof t === "string") return t;
  if (t && t.year) return `${t.year}-${String(t.month).padStart(2, "0")}-${String(t.day).padStart(2, "0")}`;
  return typeof t === "number" ? new Date(t * 1000).toISOString().slice(0, 10) : "";
}
function toWeekly(bars) {
  const out = [];
  let cur = null, key = null;
  for (const [d, o, h, l, c, v] of bars) {
    const dt = new Date(d + "T00:00:00Z");
    const monday = new Date(dt); monday.setUTCDate(dt.getUTCDate() - ((dt.getUTCDay() + 6) % 7));
    const k = monday.toISOString().slice(0, 10);
    if (k !== key) { if (cur) out.push(cur); key = k; cur = [d, o, h, l, c, v]; }
    else { cur[2] = Math.max(cur[2], h); cur[3] = Math.min(cur[3], l); cur[4] = c; cur[5] += v; }
  }
  if (cur) out.push(cur);
  return out;
}
function futureTimes(last, n, weekly) {        // the next n weekdays (or weeks) after `last`, as "YYYY-MM-DD"
  if (!last) return [];
  const out = [], d = new Date(last + "T00:00:00Z");
  while (out.length < n) {
    d.setUTCDate(d.getUTCDate() + (weekly ? 7 : 1));
    if (!weekly && (d.getUTCDay() === 0 || d.getUTCDay() === 6)) continue;
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}
function sma(bars, n) {
  const out = []; let s = 0;
  for (let i = 0; i < bars.length; i++) {
    s += bars[i][4]; if (i >= n) s -= bars[i - n][4];
    if (i >= n - 1) out.push({time: bars[i][0], value: s / n});
  }
  return out;
}

// el: container; payload: /api/scr/bars response. Returns a handle with setTF / reset / addR1 / chart.
function buildChart(el, payload, tf, opts = {}) {
  const chart = LightweightCharts.createChart(el, {
    autoSize: true,
    layout: {background: {color: "#ffffff"}, textColor: "#131722", fontSize: opts.small ? 10 : 12},
    grid: {vertLines: {color: "#f0f3fa"}, horzLines: {color: "#f0f3fa"}},
    rightPriceScale: {borderColor: "#e0e3eb", scaleMargins: {top: 0.08, bottom: 0.22}},
    timeScale: {borderColor: "#e0e3eb", rightOffset: 3, minBarSpacing: 0.2, shiftVisibleRangeOnNewBar: false},
    crosshair: {mode: LightweightCharts.CrosshairMode.Normal},
    handleScroll: true, handleScale: true,
    // dates as yyyy-mm-dd like the recorder. No custom price-label formatter: any custom formatter (global or on
    // the candle series) shifted the volume bars up off the date axis in lightweight-charts 4.1.3.
    localization: {dateFormat: "yyyy-MM-dd", timeFormatter: ymd},
  });
  chart.applyOptions({timeScale: {tickMarkFormatter: t => ymd(t)}});
  const candles = chart.addCandlestickSeries({upColor: COL.up, downColor: COL.down, borderVisible: false,
                                              wickUpColor: COL.up, wickDownColor: COL.down});
  const s10 = chart.addLineSeries({color: COL.sma10, lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false});
  const s20 = chart.addLineSeries({color: COL.sma20, lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false});
  const vol = chart.addHistogramSeries({priceScaleId: "vol", priceFormat: {type: "volume"}, lastValueVisible: false, priceLineVisible: false});
  chart.priceScale("vol").applyOptions({scaleMargins: {top: 0.82, bottom: 0}});
  const extra = [];
  const h = {chart, candles, tf, bars: [], priceLines: [], el, after: []};   // after: re-run on every setTF (drawings)

  h.setTF = (t) => {
    h.tf = t;
    const b = TF[t].weekly ? toWeekly(payload.bars) : payload.bars;
    h.bars = b;
    // empty future slots after the last candle (whitespace data) so a drawing can end out in the blank area, like
    // TradingView: ~6 months of weekdays on daily charts, a year of weeks on weekly. h.slots = every time on the axis.
    const fut = futureTimes(b.length ? b[b.length - 1][0] : null, TF[t].weekly ? 52 : 126, TF[t].weekly);
    h.slots = b.map(x => x[0]).concat(fut);
    candles.setData(b.map(([time, open, high, low, close]) => ({time, open, high, low, close})).concat(fut.map(time => ({time}))));
    s10.setData(sma(b, 10)); s20.setData(sma(b, 20));
    vol.setData(b.map(([time, o, , , c, v]) => ({time, value: v, color: c >= o ? "rgba(8,153,129,0.35)" : "rgba(242,54,69,0.35)"})));
    extra.forEach(s => chart.removeSeries(s)); extra.length = 0;
    if (opts.overlays) drawOverlays(); else candles.setMarkers([]);
    h.after.forEach(fn => fn());
    h.reset();
  };
  h.reset = () => {
    const n = h.bars.length, want = TF[h.tf].bars;
    // leave ~12% blank space after the last candle (room to draw / drag lines into the future, like TradingView)
    if (n) chart.timeScale().setVisibleLogicalRange({from: Math.max(-1, n - want), to: n + Math.max(4, Math.round(want * 0.12))});
    chart.priceScale("right").applyOptions({autoScale: true});
  };
  h.addR1 = (price, title, color = COL.r1, style = 2) => {
    const pl = candles.createPriceLine({price, color, lineWidth: 1, lineStyle: style, axisLabelVisible: true, title});
    h.priceLines.push(pl); return pl;
  };
  h.clearR1 = () => { h.priceLines.forEach(p => candles.removePriceLine(p)); h.priceLines = []; };

  function snap(d) {   // first bar time on/after d in the current series (weekly-safe)
    const b = h.bars.find(x => x[0] >= d);
    return b ? b[0] : null;
  }
  function drawOverlays() {
    const marks = [];
    for (const e of payload.earnings || []) {
      const t = snap(e); if (t) marks.push({time: t, position: "belowBar", color: COL.earn, shape: "circle", text: "E"});
    }
    for (const f of payload.flags || []) {
      if (f.r1 && f.r1_date) {
        const a = snap(f.r1_date), z = snap(f.end || f.conf);
        if (a && z && a <= z) {
          const s = chart.addLineSeries({color: COL.flag, lineWidth: 2, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false});
          s.setData(a === z ? [{time: a, value: f.r1}] : [{time: a, value: f.r1}, {time: z, value: f.r1}]);
          extra.push(s);
        }
      }
      const c = snap(f.conf);
      if (c) marks.push({time: c, position: "aboveBar", color: PAT_COLOR[f.pattern] || COL.flag, shape: "arrowDown",
                         text: (f.pattern || "flag") + " (" + f.src + ")"});
    }
    marks.sort((x, y) => x.time < y.time ? -1 : x.time > y.time ? 1 : 0);
    candles.setMarkers(marks);
  }
  h.setTF(tf);
  // A chart built before its box has a width ignores the range set above and falls back to the default bar spacing
  // (~50 bars, which looked like "3M" whatever button was selected). Re-apply the selected range once the box is
  // actually laid out (only until the user zooms / scrolls it themselves).
  let touched = false;
  el.addEventListener("wheel", () => { touched = true; }, {passive: true});
  el.addEventListener("pointerdown", () => { touched = true; });
  let lastW = el.clientWidth;
  const ro = new ResizeObserver(() => {
    const w = el.clientWidth;
    if (!el.isConnected) return ro.disconnect();
    if (w > 0 && w !== lastW && !touched) requestAnimationFrame(() => h.reset());
    lastW = w;
  });
  ro.observe(el);
  requestAnimationFrame(() => { if (!touched && el.clientWidth > 0) h.reset(); });
  return h;
}

// ---------------------------------------------------------------- drawings
// Alt+T trendline (2 clicks), Alt+H horizontal line (1 click), Delete / Backspace removes the drawing under the
// cursor, Esc cancels. Works on whichever chart the mouse is over. Saved per ticker on the server
// (local_recorder/drawings.json); every chart showing that ticker -- grid, armed mini charts, full chart, other
// tabs -- redraws when one changes. Stored as dates + prices: {type:"trend", a:[date, price], b:[date, price]} or
// {type:"hline", price}.
// sel: the drawing you clicked on {h, i} -- shown thicker with its end points, Delete removes it (like TradingView)
const DRAW = {store: new Map(), handles: new Set(), active: null, mode: null, first: null, lastDraw: 0, sel: null, drag: null};
const DRAW_COLOR = "#2962ff";

async function drawingsLoad(tickers, force = false) {
  const need = [...new Set(tickers)].filter(t => force || !DRAW.store.has(t));
  if (!need.length) return;
  let d = {};
  try { d = await getJSON("/api/scr/drawings?t=" + encodeURIComponent(need.join(","))); }
  catch (e) { console.warn("drawings unavailable (old server running?)", e); }   // charts still load, just no drawings
  for (const t of need) DRAW.store.set(t, d[t] || []);
}
const nowLocal = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 19);
async function drawingsSave(t) {
  await postJSON("/api/scr/drawings", {ticker: t, drawings: DRAW.store.get(t) || []});
  drawingsRefresh(t);
  if (CHAN) CHAN.postMessage({type: "drawings", ticker: t});
  window.dispatchEvent(new CustomEvent("drawings-changed", {detail: t}));   // screener: refresh "Recently drawn"
}
function drawingsRefresh(t) { for (const h of DRAW.handles) if (h.ticker === t) h.renderDrawings(); }
function drawingBusy() { return !!DRAW.mode || Date.now() - DRAW.lastDraw < 400; }   // chart.html: don't set R1 then
function drawSelect(h, i) {      // h = null clears the selection
  const old = DRAW.sel;
  DRAW.sel = h && i >= 0 ? {h, i} : null;
  if (old && old.h !== h) old.h.renderDrawings();
  if (h) h.renderDrawings();
}
if (CHAN) CHAN.addEventListener("message", e => {
  if (e.data && e.data.type === "drawings")
    drawingsLoad([e.data.ticker], true).then(() => {
      drawingsRefresh(e.data.ticker);
      window.dispatchEvent(new CustomEvent("drawings-changed", {detail: e.data.ticker}));
    });
});

function drawToast(text) {
  let t = document.getElementById("drawToast");
  if (!t) {
    t = document.createElement("div"); t.id = "drawToast";
    t.style.cssText = "position:fixed;left:50%;bottom:18px;transform:translateX(-50%);background:#131722;color:#fff;" +
                      "padding:7px 14px;border-radius:6px;font:12px sans-serif;z-index:99;pointer-events:none";
    document.body.appendChild(t);
  }
  t.textContent = text || ""; t.style.display = text ? "block" : "none";
}
function drawCancel() {
  // leave drawing mode BEFORE touching the preview: setData fires the chart's crosshair-move event synchronously,
  // and a still-active trend mode would redraw the preview from inside that event (2026-11-25 stack overflow)
  const h = DRAW.active;
  DRAW.mode = null; DRAW.first = null; drawToast("");
  if (h && h.tmp) h.tmp.setData([]);
  for (const h of DRAW.handles) h.el.style.cursor = "";
}

// attach drawing support to a buildChart handle for one ticker; call h.detach() before chart.remove()
function attachDrawings(h, ticker) {
  h.ticker = ticker; h.dseries = []; h.dlines = []; h.mouse = null;
  h.tmp = h.chart.addLineSeries({color: DRAW_COLOR, lineWidth: 1, lineStyle: 2, lastValueVisible: false,
                                 priceLineVisible: false, crosshairMarkerVisible: false, autoscaleInfoProvider: () => null});
  DRAW.handles.add(h);
  h.el.addEventListener("mouseenter", () => { if (!DRAW.mode) DRAW.active = h; });

  const mapT = d => {            // a stored date -> the bar on/before it in this chart's series (daily or weekly)
    let t = null;
    for (const x of h.slots) { if (x <= d) t = x; else break; }
    return t;
  };
  const pointAt = p => {         // click / crosshair point -> [bar date, price]
    let t = p.time ? ymd(p.time) : null;
    if (!t) {
      const lg = h.chart.timeScale().coordinateToLogical(p.point.x);
      if (lg == null || !h.slots.length) return null;
      t = h.slots[Math.max(0, Math.min(h.slots.length - 1, Math.round(lg)))];
    }
    const price = h.candles.coordinateToPrice(p.point.y);
    return price == null ? null : [t, +price.toFixed(4)];
  };
  const seg = (a, b) => a[0] === b[0] ? [] : (a[0] < b[0] ? [a, b] : [b, a]).map(([time, value]) => ({time, value}));

  h.renderDrawings = () => {
    // removing / re-adding line series makes the chart re-position its view: keep the view exactly where it was
    const vr = h.chart.timeScale().getVisibleLogicalRange();
    h.dseries.forEach(s => h.chart.removeSeries(s)); h.dseries = []; h.dsByIdx = {};
    h.dlines.forEach(l => h.candles.removePriceLine(l)); h.dlines = [];
    const selI = DRAW.sel && DRAW.sel.h === h ? DRAW.sel.i : -1;
    (DRAW.store.get(ticker) || []).forEach((d, i) => {
      const sel = i === selI;
      if (d.type === "hline") {
        h.dlines.push(h.candles.createPriceLine({price: d.price, color: DRAW_COLOR, lineWidth: sel ? 3 : 1, lineStyle: 0,
                                                 axisLabelVisible: true, title: sel ? "selected" : ""}));
      } else if (d.type === "trend") {
        const ta = mapT(d.a[0]), tb = mapT(d.b[0]);
        if (!ta || !tb || ta === tb) return;             // outside this chart's dates (e.g. a later replay date)
        const s = h.chart.addLineSeries({color: DRAW_COLOR, lineWidth: sel ? 3 : 2, lastValueVisible: false,
                                         priceLineVisible: false, crosshairMarkerVisible: false,
                                         pointMarkersVisible: sel, pointMarkersRadius: 4, autoscaleInfoProvider: () => null});
        s.setData(seg([ta, d.a[1]], [tb, d.b[1]]));
        h.dseries.push(s); h.dsByIdx[i] = s;
      }
    });
    if (vr) h.chart.timeScale().setVisibleLogicalRange(vr);
  };
  h.updateDrawing = i => {          // move one existing trendline in place (used while dragging: no remove / re-add)
    const d = (DRAW.store.get(ticker) || [])[i], s = h.dsByIdx && h.dsByIdx[i];
    if (!d || d.type !== "trend" || !s) return h.renderDrawings();
    const ta = mapT(d.a[0]), tb = mapT(d.b[0]);
    if (!ta || !tb || ta === tb) return;
    const vr = h.chart.timeScale().getVisibleLogicalRange();
    s.setData(seg([ta, d.a[1]], [tb, d.b[1]]));
    if (vr) h.chart.timeScale().setVisibleLogicalRange(vr);
  };
  h.after.push(h.renderDrawings);

  let inMove = false;     // tmp.setData re-fires crosshair-move synchronously: without this guard it recursed forever
  h.chart.subscribeCrosshairMove(p => {
    if (inMove) return;
    h.mouse = p.point || null;
    if (!DRAW.mode && !DRAW.drag) h.el.style.cursor = h.mouse && h.nearest() >= 0 ? "move" : "";
    if (DRAW.mode === "trend" && DRAW.first && DRAW.active === h && p.point) {
      const q = pointAt(p);
      if (q) { inMove = true; try { h.tmp.setData(seg(DRAW.first, q)); } finally { inMove = false; } }
    }
  });
  h.chart.subscribeClick(p => {
    if (!DRAW.mode) {                      // not drawing: a click on a line selects it, anywhere else deselects
      h.mouse = p.point || h.mouse;
      const i = p.point ? h.nearest() : -1;
      if (i >= 0) { DRAW.lastDraw = Date.now(); drawSelect(h, i); }   // lastDraw: chart.html won't take it as an R1 pick
      else if (DRAW.sel) drawSelect(null);
      return;
    }
    if (DRAW.active !== h || !p.point) return;
    const q = pointAt(p);
    if (!q) return;
    const list = DRAW.store.get(ticker) || [];
    if (DRAW.mode === "hline") {
      list.push({type: "hline", price: q[1], at: nowLocal()});
    } else if (!DRAW.first) {
      DRAW.first = q; drawToast("Trendline: click the second point (Esc cancels)"); return;
    } else {
      if (q[0] === DRAW.first[0]) return;                 // same bar twice: wait for a different one
      list.push({type: "trend", a: DRAW.first, b: q, at: nowLocal()});
    }
    DRAW.store.set(ticker, list);
    DRAW.lastDraw = Date.now();
    drawCancel();
    drawingsSave(ticker);
  });

  h.nearest = () => {             // index of the drawing under the cursor (within 8 px), else -1
    if (!h.mouse) return -1;
    const {x, y} = h.mouse, ts = h.chart.timeScale();
    let best = -1, bd = 8;
    (DRAW.store.get(ticker) || []).forEach((d, i) => {
      let dist = Infinity;
      if (d.type === "hline") {
        const yy = h.candles.priceToCoordinate(d.price); if (yy != null) dist = Math.abs(y - yy);
      } else {
        const ta = mapT(d.a[0]), tb = mapT(d.b[0]);
        const x1 = ta && ts.timeToCoordinate(ta), x2 = tb && ts.timeToCoordinate(tb);
        const y1 = h.candles.priceToCoordinate(d.a[1]), y2 = h.candles.priceToCoordinate(d.b[1]);
        if ([x1, x2, y1, y2].every(v => v != null)) {
          const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy;
          const u = L ? Math.max(0, Math.min(1, ((x - x1) * dx + (y - y1) * dy) / L)) : 0;
          dist = Math.hypot(x - (x1 + u * dx), y - (y1 + u * dy));
        }
      }
      if (dist < bd) { bd = dist; best = i; }
    });
    return best;
  };
  // ---- drag to edit (like TradingView): press on a line and drag. Near an end point of a trendline -> moves that end;
  // elsewhere on it -> moves the whole line; a horizontal line moves up / down. Pointer events are caught in the
  // CAPTURE phase on the container so the chart never sees the press and doesn't pan; saved on release.
  const ts = () => h.chart.timeScale();
  const barIdx = d => { const t = mapT(d); return t ? h.slots.indexOf(t) : -1; };
  const dateAtX = x => {
    const lg = ts().coordinateToLogical(x);
    return lg == null ? null : h.slots[Math.max(0, Math.min(h.slots.length - 1, Math.round(lg)))];
  };
  const shift = (d, n) => { const i = barIdx(d); return i < 0 ? d : h.slots[Math.max(0, Math.min(h.slots.length - 1, i + n))]; };
  const onDown = e => {
    if (DRAW.mode || e.button !== 0) return;
    const r = h.el.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    h.mouse = {x, y};
    const i = h.nearest();
    if (i < 0) return;                                   // not on a line: let the chart handle it (pan / click)
    e.stopPropagation(); e.preventDefault();
    const list = DRAW.store.get(ticker), d = list[i], orig = JSON.parse(JSON.stringify(d));
    let part = "line";
    if (d.type === "trend") {
      const ta = mapT(d.a[0]), tb = mapT(d.b[0]);
      const pa = [ts().timeToCoordinate(ta), h.candles.priceToCoordinate(d.a[1])];
      const pb = [ts().timeToCoordinate(tb), h.candles.priceToCoordinate(d.b[1])];
      if (pa[0] != null && Math.hypot(x - pa[0], y - pa[1]) < 10) part = "a";
      else if (pb[0] != null && Math.hypot(x - pb[0], y - pb[1]) < 10) part = "b";
    }
    DRAW.drag = {h, i}; DRAW.lastDraw = Date.now();
    // the chart must not pan or zoom while a line is being dragged (it used to slide along when dragging right)
    h.chart.applyOptions({handleScroll: false, handleScale: false});
    drawSelect(h, i);
    h.el.style.cursor = "grabbing";
    let moved = false;
    const move = ev => {
      const xx = ev.clientX - r.left, yy = ev.clientY - r.top;
      if (!moved && Math.hypot(xx - x, yy - y) < 3) return;
      moved = true;
      const p1 = h.candles.coordinateToPrice(yy), p0 = h.candles.coordinateToPrice(y);
      if (p1 == null || p0 == null) return;
      if (d.type === "hline") d.price = +p1.toFixed(4);
      else if (part === "a" || part === "b") { const t = dateAtX(xx); if (t) d[part] = [t, +p1.toFixed(4)]; }
      else {
        const l0 = ts().coordinateToLogical(x), l1 = ts().coordinateToLogical(xx);
        const n = l0 == null || l1 == null ? 0 : Math.round(l1 - l0), dp = p1 - p0;
        d.a = [shift(orig.a[0], n), +(orig.a[1] + dp).toFixed(4)];
        d.b = [shift(orig.b[0], n), +(orig.b[1] + dp).toFixed(4)];
      }
      if (d.type === "trend") h.updateDrawing(i); else h.renderDrawings();
      ev.preventDefault();
    };
    const up = () => {
      window.removeEventListener("pointermove", move, true); window.removeEventListener("pointerup", up, true);
      DRAW.drag = null; DRAW.lastDraw = Date.now(); h.el.style.cursor = "move";
      h.chart.applyOptions({handleScroll: true, handleScale: true});
      if (!moved) return;                                // a plain click: just selected
      if (d.type === "trend" && d.a[0] === d.b[0]) Object.assign(d, orig);   // ends on the same bar: undo
      else d.at = nowLocal();                                                 // edited -> counts as recently drawn
      drawingsSave(ticker);
    };
    window.addEventListener("pointermove", move, true); window.addEventListener("pointerup", up, true);
  };
  h.el.addEventListener("pointerdown", onDown, true);
  // the chart also listens to mousedown / touchstart: swallow those while a drag started on a line
  for (const ev of ["mousedown", "touchstart"]) h.el.addEventListener(ev, e => { if (DRAW.drag && DRAW.drag.h === h) e.stopPropagation(); }, true);

  h.detach = () => {
    DRAW.handles.delete(h);
    if (DRAW.sel && DRAW.sel.h === h) DRAW.sel = null;
    if (DRAW.active === h) { drawCancel(); DRAW.active = null; }
  };
  h.renderDrawings();
}

document.addEventListener("keydown", e => {
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "select" || tag === "textarea") return;
  if (e.altKey && (e.code === "KeyT" || e.code === "KeyH")) {
    e.preventDefault();
    if (!DRAW.active) { drawToast("Move the mouse over a chart first"); setTimeout(() => drawToast(""), 1500); return; }
    drawCancel();
    DRAW.mode = e.code === "KeyT" ? "trend" : "hline";
    DRAW.active.el.style.cursor = "crosshair";
    drawToast(DRAW.mode === "trend" ? `Trendline on ${DRAW.active.ticker}: click the first point (Esc cancels)`
                                    : `Horizontal line on ${DRAW.active.ticker}: click a price (Esc cancels)`);
  } else if (e.key === "Escape" && (DRAW.mode || DRAW.sel)) {
    if (DRAW.mode) drawCancel(); else drawSelect(null);
  } else if ((e.key === "Delete" || e.key === "Backspace") && !DRAW.mode) {
    // the selected line first (clicked on, like TradingView); else the line under the cursor
    const tgt = DRAW.sel ? DRAW.sel : (DRAW.active ? {h: DRAW.active, i: DRAW.active.nearest()} : null);
    if (tgt && tgt.i >= 0 && (DRAW.store.get(tgt.h.ticker) || [])[tgt.i]) {
      e.preventDefault();
      DRAW.store.get(tgt.h.ticker).splice(tgt.i, 1);
      DRAW.sel = null;
      drawingsSave(tgt.h.ticker);
    }
  }
});
