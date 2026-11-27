"""
Emits the N-slot HTF Manual Flag Recorder as Pine Script.

Pine can't declare inputs in a loop, so the per-slot input block has to be spelled out;
everything else in the script is array-driven and doesn't change with N. Generating it
beats hand-editing ten near-identical blocks.

    python generate_recorder.py            # 10 slots -> htf_manual_flag_recorder_v2.pine
    python generate_recorder.py --slots 5
"""
import argparse
import os

DEFAULT_DATE = "2000-01-03"  # same for start/conf/end so an unplaced slot reads as unused
# Resistance source bars default to a date no chart has a bar on, so "not set" is detectable:
# no matching bar -> derived price is na -> no line drawn, nothing exported.
NO_BAR_DATE = "1900-01-02"


PATTERNS = ["Green", "Red", "Perfect", "Big Green", "Big Red", "Big Perfect"]  # export codes 1..6
AUTO = "Auto"


def pattern_input(i: int) -> str:
    # Replaced the HL_FLAG / LOWER_LOW "Setup type" dropdown (2026-11-06): Red / Big Red are the
    # lower-low setups, every other pattern is a higher-low one. Same input slot the old dropdown
    # had, so charts saved with the old recorder keep their clicks (only the dropdown resets).
    # Schema 5 (2026-11-10): "Auto" (default) replaces "Not set" -- the recorder classifies the
    # flag itself (autoPat, a port of htf_pattern_labeler.py) and shows it on the box; picking a
    # pattern overrides it. Pine can't write an input, so the dropdown itself stays on Auto.
    opts = ", ".join(f'"{x}"' for x in [AUTO] + PATTERNS)
    tip = '"Auto = the recorder picks the pattern (shown on the box as \\"(auto)\\"). Pick one here only to override it."'
    return f'f{i}_pat     = input.string("{AUTO}", "Pattern", options = [{opts}], tooltip = {tip}, group = "Flag {i}")'


# Port of htf_pattern_labeler.label_flag(). Bar highs/lows are kept in arrays indexed by
# bar_index, so a flag of any age can be read on the last bar (history references cap at
# 5000 bars back; 20-year daily charts run past that). Checked against the Python labeler
# on all 2,192 annotated flags via an array/loop mirror (2,192 / 2,192 match, 2026-11-10).
# Keep both in sync: thresholds below = TOP_LOOKBACK, BASE_LOOKBACK, RETRACE_FLAG,
# SPIKY_BREAKS, DOWNTREND_LOW_POS there.
AUTO_PINE = r'''
// ---- Auto pattern (port of htf_pattern_labeler.py -- keep the two in sync) ----
var float[] bH = array.new_float()
var float[] bL = array.new_float()

argMaxH(int a, int b) =>
    int k = a
    float m = array.get(bH, a)
    if b > a
        for j = a + 1 to b
            if array.get(bH, j) > m
                m := array.get(bH, j)
                k := j
    k

argMinL(int a, int b) =>
    int k = a
    float m = array.get(bL, a)
    if b > a
        for j = a + 1 to b
            if array.get(bL, j) < m
                m := array.get(bL, j)
                k := j
    k

// Swing point: beats (or ties) both neighbours. Only called with a < j < b, never at an edge.
isPiv(int j, bool hi) =>
    hi ? array.get(bH, j) >= array.get(bH, j - 1) and array.get(bH, j) >= array.get(bH, j + 1) : array.get(bL, j) <= array.get(bL, j - 1) and array.get(bL, j) <= array.get(bL, j + 1)

pv(int j, bool hi) => hi ? array.get(bH, j) : array.get(bL, j)

// Least-squares slope through the window's swing points (all bars if fewer than 2), as % of
// mean price per bar; na if under 2 points. |slope| < 1e-9 -> 0 so a flat top reads flat.
slopeN(int a, int b, bool hi) =>
    int nPiv = 0
    if b - 1 >= a + 1
        for j = a + 1 to b - 1
            if isPiv(j, hi)
                nPiv += 1
    bool usePiv = nPiv >= 2
    int n = 0
    float sx = 0.0
    float sy = 0.0
    for j = a to b
        bool take = not usePiv
        if usePiv and j > a and j < b
            take := isPiv(j, hi)
        if take
            n += 1
            sx += j
            sy += pv(j, hi)
    float res = na
    if n >= 2
        float mx = sx / n
        float my = sy / n
        float sxy = 0.0
        float sxx = 0.0
        for j = a to b
            bool take = not usePiv
            if usePiv and j > a and j < b
                take := isPiv(j, hi)
            if take
                sxy += (j - mx) * (pv(j, hi) - my)
                sxx += (j - mx) * (j - mx)
        res := sxy / sxx / my * 100
        res := math.abs(res) < 1e-9 ? 0.0 : res
    res

// s = flag-start bar, cIdx = confirmed bar, stopIdx = R1-break bar (else the later of end /
// confirmed). Returns a pattern code 1..6, or 0 = no confident match (Spiky / Expanding).
autoPat(int s, int cIdx, int stopIdx) =>
    int last = array.size(bH) - 1
    int e = math.min(math.max(s + 2, stopIdx - 1), last)
    int c = math.min(e, math.max(s, na(cIdx) ? s : cIdx))
    int topI = argMaxH(math.max(0, s - 15), s)
    float preTop = array.get(bH, topI)
    int winTop = argMaxH(s, c)
    int breaks = 0
    if e - 1 >= s + 1
        for j = s + 1 to e - 1
            if isPiv(j, true) and array.get(bH, j) > preTop
                breaks += 1
    bool late = float(winTop - s) / math.max(1, c - s) > 0.5
    bool spiky = breaks >= 2 and late
    float base = array.get(bL, argMinL(math.max(0, topI - 60), topI))
    float wLow = array.get(bL, argMinL(s, e))
    float retr = preTop > base ? (preTop - wLow) / (preTop - base) : na
    if not na(retr) and retr < 0.40 and array.get(bH, winTop) > preTop and not spiky
        topI := winTop
    int w0 = s < topI and topI < e - 1 ? topI : s
    int loI = argMinL(w0, e)
    float lowPos = float(loI - s) / math.max(1, e - s)
    int code = 0
    if not na(retr) and retr >= 0.40
        if lowPos >= 0.40
            code := 5
        else
            float hs = e - loI + 1 >= 2 ? slopeN(loI, e, true) : slopeN(topI, e, true)
            code := not na(hs) and hs > 0 ? 4 : 6
    else
        float hs = slopeN(w0, e, true)
        float ls = slopeN(w0, e, false)
        if not spiky and not na(hs) and not na(ls)
            code := hs > 0 and ls > 0 ? 1 : hs <= 0 and ls > 0 ? 3 : hs <= 0 and ls <= 0 ? 2 : 0
    code
'''


def slot_inputs(i: int) -> list:
    g = f'"Flag {i}"'
    d = f'timestamp("{DEFAULT_DATE}")'
    nb = f'timestamp("{NO_BAR_DATE}")'
    tip = '"The confirmed date (click 2) -- when the level goes live and you start watching for the break."'
    rtip = '"Click the candle whose HIGH is the level. The high is read from that bar -- no need to place the price by eye."'
    return [
        f'f{i}_on      = input.bool(true, "Enabled", group = {g})',
        pattern_input(i),
        f'f{i}_start   = input.time({d}, "1. Start", group = {g}, confirm = true)',
        f'f{i}_conf    = input.time({d}, "2. Confirmed (HL or LL)", group = {g}, confirm = true)',
        f'f{i}_end     = input.time({d}, "3. End / reclaim end", group = {g}, confirm = true)',
        f'f{i}_r1_bar  = input.time({nb}, "4. R1 candle (its high = level)", tooltip = {rtip}, group = {g}, confirm = true)',
        f'f{i}_r1_same = input.bool(true, "R1 effective = auto", tooltip = {tip}, group = {g})',
        f'f{i}_r1_alt  = input.time({d}, "R1 effective (override)", group = {g})',
        f'f{i}_r2_bar  = input.time({nb}, "R2 candle (its high = level)", group = {g})',
        f'f{i}_r2_date = input.time({d}, "R2 effective", group = {g})',
        "",
    ]


def slot_register(i: int) -> str:
    return (f"    addSlot(f{i}_on, f{i}_pat, f{i}_start, f{i}_conf, f{i}_end, f{i}_r1_bar, "
            f"f{i}_r1_same, f{i}_r1_alt, f{i}_r2_bar, f{i}_r2_date)")


def build(n: int) -> str:
    L = []
    L += [
        "//@version=6",
        f"// HTF Manual Flag Recorder — {n} slots. GENERATED by generate_recorder.py; edit that, not this.",
        "//",
        "// Records discretionary flag annotations inside TradingView and publishes them as a",
        "// KEY/VALUE stream on the final bars so Chart Data Export carries them to CSV. Two plots",
        "// regardless of slot count (Pine caps a script at 64). Dates are YYYYMMDD. See README.md.",
        "//",
        "// Every slot's default start/confirmed/end are the SAME date, which the script treats as",
        "// unused -- so if the placement popup's x button finishes the add with defaults, hitting",
        "// it after your last real flag leaves the remaining slots empty. If it instead cancels",
        "// the whole add, spam-click one candle through the leftover prompts; same result.",
        "",
        # Per slot: 1 box, 1 label, and up to 3 lines (confirmed marker + R1 + R2). Scaled with
        # headroom rather than hardcoded -- at 20 slots the old fixed max_labels_count of 20 sat
        # exactly on the cap, where Pine starts silently dropping the oldest drawings.
        f'indicator("HTF Manual Flag Recorder ({n})", overlay = true, '
        f'max_boxes_count = {min(500, max(50, n * 2))}, '
        f'max_lines_count = {min(500, max(150, n * 6))}, '
        f'max_labels_count = {min(500, max(50, n * 2))})',
        "",
        "// Schema 3 drops the review-status field (key 2) that schema 2 carried. Reviewed-ness",
        "// is now implied by the export existing at all: a downloaded chart means flags were",
        "// found, and a ticker never exported means none were.",
        "// Schema 4 adds field 10: the pattern picked per slot (1 Green, 2 Red, 3 Perfect,",
        "// 4 Big Green, 5 Big Red, 6 Big Perfect; na = not set).",
        "// Schema 5: na in field 10 now means Auto -- the pattern was left to the recorder, and",
        "// field 2 is 0 (setup derived at ingest from the auto pattern). ingest_exports.py",
        "// re-runs the same classifier on the exported bars, so the export needs nothing more.",
        "SCHEMA_VERSION = 5",
        f"N_SLOTS = {n}",
        "",
        'G_DISP   = "Display"',
        "",
        'showTable    = input.bool(true, "Show summary table", group = G_DISP)',
        'boxPad       = input.float(1.0, "Box padding %", minval = 0.0, maxval = 10.0, group = G_DISP)',
        '// Spanning fewer than this many calendar days means the slot was skipped, not drawn.',
        '// Spam-clicking one candle to burn leftover prompts gives a 0-day span, but the mouse',
        '// drifts -- a few days of slop still reads as "skipped" so a stray click cannot create a',
        '// junk flag. Real flags run weeks, so this cannot swallow a genuine one.',
        'minSpan      = input.int(5, "Min flag span (days)", minval = 0, group = G_DISP)',
        "",
        "// Same four clicks serve every pattern; the Pattern dropdown (set afterward) decides how",
        "// they're read. Green / Perfect / Big Green / Big Perfect = higher-low setup: start /",
        "// higher-low confirmed / final end / R1. Red / Big Red = lower-low setup: start / lower-low",
        "// confirmed / reclaim end / R1 (reclaim only); click 3 on the same bar as click 2 = no",
        "// reclaim, and the script derives LL_NO_RECLAIM vs LL_RECLAIM itself.",
    ]
    for i in range(1, n + 1):
        L += slot_inputs(i)

    L += [
        'tlabel(code) => code == 1 ? "HL" : code == 2 ? "LL fail" : "LL reclaim"',
        "ymd(t) => na(t) ? float(na) : float(year(t) * 10000 + month(t) * 100 + dayofmonth(t))",
        'md(t) => str.tostring(month(t)) + "/" + str.tostring(dayofmonth(t))',
        'mdy(t) => md(t) + "/" + str.tostring(year(t) % 100)',
        f'NO_BAR = ymd(timestamp("{NO_BAR_DATE}"))  // sentinel: resistance candle not set',
        "",
        "var bool[]   sOn     = array.new<bool>()",
        "var int[]    sStart  = array.new<int>()",
        "var int[]    sConf   = array.new<int>()",
        "var int[]    sEnd    = array.new<int>()",
        "var int[]    sR1bar  = array.new<int>()",
        "var bool[]   sR1same = array.new<bool>()",
        "var int[]    sR1alt  = array.new<int>()",
        "var int[]    sR2bar  = array.new<int>()",
        "var int[]    sR2date = array.new<int>()",
        "var int[]    sPat    = array.new<int>()",
        "",
        "// Pattern name -> code 1..6, 0 = not set.",
        "patCode(string p) => " + " : ".join(f'p == "{x}" ? {k}' for k, x in enumerate(PATTERNS, 1)) + " : 0",
        'patName(int c) => ' + " : ".join(f'c == {k} ? "{x}"' for k, x in enumerate(PATTERNS, 1)) + ' : ""',
        "",
        "addSlot(bool on, string pat, int tStart, int tConf, int tEnd, int r1bar, bool r1same, int r1alt, int r2bar, int r2date) =>",
        "    array.push(sOn, on)",
        "    array.push(sStart, tStart)",
        "    array.push(sConf, tConf)",
        "    array.push(sEnd, tEnd)",
        "    array.push(sR1bar, r1bar)",
        "    array.push(sR1same, r1same)",
        "    array.push(sR1alt, r1alt)",
        "    array.push(sR2bar, r2bar)",
        "    array.push(sR2date, r2date)",
        "    array.push(sPat, patCode(pat))",
        "",
        "if barstate.isfirst",
    ]
    for i in range(1, n + 1):
        L.append(slot_register(i))

    L += [
        "",
        "// Derived per slot, computed once. Type codes: 1 HL_FLAG, 2 LL_NO_RECLAIM, 3 LL_RECLAIM.",
        "// Start/end are sorted so clicking end-before-start still yields a box. A slot whose",
        "// start and end land on the same bar is unused -- the spam-click / default-value skip.",
        "var int[]   dT0     = array.new<int>()",
        "var int[]   dT1     = array.new<int>()",
        "var bool[]  dUsed   = array.new<bool>()",
        "var int[]   dCode   = array.new<int>()",
        "var int[]   dR1date = array.new<int>()",
        "var bool[]  dReclm  = array.new<bool>()",
        "var float[] aHi     = array.new<float>()",
        "var float[] aLo     = array.new<float>()",
        "var float[] aR1px   = array.new<float>()",
        "var float[] aR2px   = array.new<float>()",
        "// Bar indices for the auto-pattern port: flag start, confirmed, later of end/confirmed,",
        "// first R1 break. dNoRecl = end on the confirmed bar (a failed lower-low, no reclaim).",
        "var int[]   iS      = array.new<int>()",
        "var int[]   iC      = array.new<int>()",
        "var int[]   iStop   = array.new<int>()",
        "var int[]   iX      = array.new<int>()",
        "var bool[]  dNoRecl = array.new<bool>()",
        "",
        "if barstate.isfirst",
        "    for i = 0 to N_SLOTS - 1",
        "        st = array.get(sStart, i)",
        "        cf = array.get(sConf, i)",
        "        en = array.get(sEnd, i)",
        "        t0 = st < en ? st : en",
        "        t1 = st < en ? en : st",
        "        used = array.get(sOn, i) and (t1 - t0) >= minSpan * 86400000",
        "        isLL = array.get(sPat, i) == 2 or array.get(sPat, i) == 5  // Red / Big Red",
        "        reclaim = isLL and ymd(en) != ymd(cf)",
        "        code = isLL ? (reclaim ? 3 : 2) : 1",
        "        // Always the confirmed date, both types. Anchoring LOWER_LOW to the reclaim-end",
        "        // instead made the level go live on the very bar it broke -- a level with no watch",
        "        // window in front of it is untestable. From the confirmed date there's a real",
        "        // window: line is live, price sits below it, the break is the entry.",
        "        r1date = array.get(sR1same, i) ? cf : array.get(sR1alt, i)",
        "        array.push(dT0, t0)",
        "        array.push(dT1, t1)",
        "        array.push(dUsed, used)",
        "        array.push(dCode, code)",
        "        array.push(dR1date, r1date)",
        "        array.push(dReclm, reclaim)",
        "        array.push(aHi, float(na))",
        "        array.push(aLo, float(na))",
        "        array.push(aR1px, float(na))",
        "        array.push(aR2px, float(na))",
        "        array.push(iS, int(na))",
        "        array.push(iC, int(na))",
        "        array.push(iStop, int(na))",
        "        array.push(iX, int(na))",
        "        array.push(dNoRecl, ymd(t1) == ymd(cf))",
        "",
    ]
    L += AUTO_PINE.strip().splitlines() + [""]
    L += [
        "// Box height comes from the bars inside each slot's date range, and each resistance level",
        "// is the HIGH of the single bar that was clicked for it. Compared as YYYYMMDD so the",
        "// clicked bar is always included regardless of the intraday moment the click landed. A",
        "// resistance bar that matches nothing (unset, default date) leaves its price na -> no line.",
        "d = ymd(time)",
        "array.push(bH, high)",
        "array.push(bL, low)",
        "for i = 0 to N_SLOTS - 1",
        "    if array.get(dUsed, i) and d >= ymd(array.get(dT0, i)) and d <= ymd(array.get(dT1, i))",
        "        h = array.get(aHi, i)",
        "        l = array.get(aLo, i)",
        "        array.set(aHi, i, na(h) ? high : math.max(h, high))",
        "        array.set(aLo, i, na(l) ? low : math.min(l, low))",
        "    if d == ymd(array.get(sR1bar, i))",
        "        array.set(aR1px, i, high)",
        "    if d == ymd(array.get(sR2bar, i))",
        "        array.set(aR2px, i, high)",
        "    if array.get(dUsed, i)",
        "        if na(array.get(iS, i)) and d >= ymd(array.get(dT0, i))",
        "            array.set(iS, i, bar_index)",
        "        if na(array.get(iC, i)) and d >= ymd(array.get(sConf, i))",
        "            array.set(iC, i, bar_index)",
        "        if na(array.get(iStop, i)) and d >= math.max(ymd(array.get(dT1, i)), ymd(array.get(sConf, i)))",
        "            array.set(iStop, i, bar_index)",
        "        r1p = array.get(aR1px, i)",
        "        if na(array.get(iX, i)) and not array.get(dNoRecl, i) and not na(r1p) and d >= ymd(array.get(dR1date, i)) and high >= r1p",
        "            array.set(iX, i, bar_index)",
        "",
        "// Effective pattern per slot: your pick, else the auto pattern (0 = auto found no match).",
        "var int[]  ePat  = array.new<int>()",
        "var bool[] eAuto = array.new<bool>()",
        "if barstate.islast",
        "    array.clear(ePat)",
        "    array.clear(eAuto)",
        "    for i = 0 to N_SLOTS - 1",
        "        int mp = array.get(sPat, i)",
        "        int ap = 0",
        "        if mp == 0 and array.get(dUsed, i)",
        "            int s0 = array.get(iS, i)",
        "            int x0 = array.get(iX, i)",
        "            int st0 = na(x0) ? array.get(iStop, i) : x0",
        "            if not na(s0) and not na(st0)",
        "                ap := autoPat(s0, array.get(iC, i), st0)",
        "        array.push(ePat, mp > 0 ? mp : ap)",
        "        array.push(eAuto, mp == 0)",
        "",
        "if barstate.islast",
        "    for i = 0 to N_SLOTS - 1",
        "        hi = array.get(aHi, i)",
        "        lo = array.get(aLo, i)",
        "        if array.get(dUsed, i) and not na(hi) and not na(lo)",
        "            t0 = array.get(dT0, i)",
        "            t1 = array.get(dT1, i)",
        "            tc = array.get(sConf, i)",
        "            pad = (hi - lo) * boxPad / 100.0",
        "            // Box color follows the pattern when one is picked -- green / red, and purple for",
        "            // the Perfect types -- and gray while no pattern is picked, so it can't be missed.",
        "            pc = array.get(ePat, i)",
        "            isA = array.get(eAuto, i)",
        "            col = pc == 3 or pc == 6 ? color.purple : pc == 1 or pc == 4 ? color.green : pc == 2 or pc == 5 ? color.red : color.gray",
        "            box.new(left = t0, top = hi + pad, right = t1, bottom = lo - pad, xloc = xloc.bar_time, border_color = color.new(col, 100), border_width = 1, bgcolor = color.new(col, 90), force_overlay = true)",
        "            line.new(x1 = tc, y1 = lo - pad, x2 = tc, y2 = hi + pad, xloc = xloc.bar_time, color = color.new(col, 70), width = 1, style = line.style_dotted, force_overlay = true)",
        "            // Slot number at the box's top edge, so a box on the chart maps back to its",
        "            // \"Flag N\" settings group -- otherwise there's no way to tell which group to",
        "            // edit when revisiting a chart with many flags. Midpoint is in time, not bar",
        "            // count, so weekend gaps shift it slightly off visual center; close enough.",
        '            label.new(x = int((t0 + t1) / 2), y = hi + pad, text = str.tostring(i + 1) + " " + (pc == 0 ? "? pick a pattern" : patName(pc) + (isA ? " (auto)" : "")), xloc = xloc.bar_time, yloc = yloc.price, style = label.style_label_down, color = color.new(col, 30), textcolor = color.white, size = size.small, force_overlay = true)',
        "            wanted = t1 + (t1 - t0)",
        "            extEnd = wanted > time ? time : wanted",
        "            isLL = pc == 2 or pc == 5",
        "            rOK = not isLL or (isA ? not array.get(dNoRecl, i) : array.get(dReclm, i))",
        "            r1px = array.get(aR1px, i)",
        "            r2px = array.get(aR2px, i)",
        "            // Drawn from the source candle so you can see which high it came from; the",
        "            // effective date (when it becomes tradeable) is carried in the export.",
        "            if rOK and not na(r1px)",
        "                line.new(x1 = array.get(sR1bar, i), y1 = r1px, x2 = extEnd, y2 = r1px, xloc = xloc.bar_time, color = color.orange, width = 2, style = line.style_dotted, force_overlay = true)",
        "            if rOK and not na(r2px)",
        "                line.new(x1 = array.get(sR2bar, i), y1 = r2px, x2 = extEnd, y2 = r2px, xloc = xloc.bar_time, color = color.blue, width = 2, style = line.style_dotted, force_overlay = true)",
        "",
        "// Export record. Key = slot*100 + field; see README for the field map.",
        "var int[]   kk = array.new_int()",
        "var float[] vv = array.new_float()",
        "",
        "push(int k, float v) =>",
        "    array.push(kk, k)",
        "    array.push(vv, v)",
        "",
        "// Resistance is exported as the SOURCE BAR DATE, not a price: the price is that bar's",
        "// high, which the parser reads from the OHLC columns of this very CSV. Deriving it here",
        "// would be wrong anyway -- the record is emitted across the final bars, so a source bar",
        "// inside that window wouldn't have been scanned yet when its slot is written.",
        "if barstate.isfirst",
        "    push(1, float(SCHEMA_VERSION))",
        "    for i = 0 to N_SLOTS - 1",
        "        b = (i + 1) * 100",
        "        u = array.get(dUsed, i)",
        "        // Auto slots export R1 whenever it's set: ingest decides lower-low/no-reclaim from",
        "        // the auto pattern (pattern isn't known yet on the first bar).",
        "        isAutoSlot = array.get(sPat, i) == 0",
        "        rOK = u and (isAutoSlot or array.get(dCode, i) == 1 or array.get(dReclm, i))",
        "        r1bar = ymd(array.get(sR1bar, i))",
        "        r2bar = ymd(array.get(sR2bar, i))",
        "        r1 = rOK and r1bar != NO_BAR",
        "        r2 = rOK and r2bar != NO_BAR",
        "        push(b + 1, u ? 1.0 : 0.0)",
        "        push(b + 2, u ? (isAutoSlot ? 0.0 : float(array.get(dCode, i))) : float(na))",
        "        push(b + 3, u ? ymd(array.get(dT0, i)) : float(na))",
        "        push(b + 4, u ? ymd(array.get(sConf, i)) : float(na))",
        "        push(b + 5, u ? ymd(array.get(dT1, i)) : float(na))",
        "        push(b + 6, r1 ? ymd(array.get(dR1date, i)) : float(na))",
        "        push(b + 7, r1 ? r1bar : float(na))",
        "        push(b + 8, r2 ? ymd(array.get(sR2date, i)) : float(na))",
        "        push(b + 9, r2 ? r2bar : float(na))",
        "        pc = array.get(sPat, i)",
        "        push(b + 10, u and pc > 0 ? float(pc) : float(na))",
        "",
        "// Record lands on the final bars so the parser finds it at a predictable end of the CSV.",
        "offset = last_bar_index - bar_index",
        "inRange = offset >= 0 and offset < array.size(kk)",
        "annoKey = inRange ? array.get(kk, offset) : int(na)",
        "annoVal = inRange ? array.get(vv, offset) : float(na)",
        "",
        'plot(annoKey, "ANNO_KEY", display = display.data_window)',
        'plot(annoVal, "ANNO_VAL", display = display.data_window)',
        "",
        "if showTable and barstate.islast",
        "    var table t = table.new(position.top_right, 2, 2, border_width = 1)",
        '    flagsTxt = ""',
        "    nSkipped = 0",
        "    for i = 0 to N_SLOTS - 1",
        "        t0 = array.get(dT0, i)",
        "        t1 = array.get(dT1, i)",
        "        // A skipped slot that spans more than a day was probably mouse drift, not a",
        "        // deliberate skip -- surfaced so it can't silently swallow a real flag.",
        "        if not array.get(dUsed, i) and (t1 - t0) > 86400000",
        "            nSkipped += 1",
        "        if array.get(dUsed, i)",
        "            pcT = array.get(ePat, i)",
        "            isAT = array.get(eAuto, i)",
        "            llT = pcT == 2 or pcT == 5",
        "            rcT = isAT ? not array.get(dNoRecl, i) : array.get(dReclm, i)",
        '            row = str.tostring(i + 1) + ": " + (pcT == 0 ? "AUTO: NO MATCH - PICK ONE" : patName(pcT) + (isAT ? " (auto)" : "")) + " / " + (llT ? (rcT ? "LL reclaim" : "LL fail") : "HL") + "  " + mdy(t0) + "-" + mdy(t1) + "  (conf " + mdy(array.get(sConf, i)) + ")"',
        '            flagsTxt := flagsTxt == "" ? row : flagsTxt + "\\n" + row',
        '    table.cell(t, 0, 0, "flags", text_color = color.gray, text_size = size.small)',
        '    table.cell(t, 1, 0, flagsTxt == "" ? "-" : flagsTxt, text_color = color.black, text_size = size.small, text_halign = text.align_left)',
        '    table.cell(t, 0, 1, "skipped", text_color = color.gray, text_size = size.small)',
        '    table.cell(t, 1, 1, nSkipped == 0 ? "-" : str.tostring(nSkipped) + " (stray clicks, under min span)", text_color = nSkipped == 0 ? color.gray : color.red, text_size = size.small)',
        "",
    ]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slots", type=int, default=10)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out = args.out or os.path.join(os.path.dirname(__file__), f"htf_recorder_{args.slots}slot.pine")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build(args.slots))
    print(f"wrote {out} ({args.slots} slots)")


if __name__ == "__main__":
    main()
