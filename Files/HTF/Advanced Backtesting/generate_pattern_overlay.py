"""
Bake htf_pattern_labels.csv into a Pine overlay so the auto-labels can be checked by eye on
TradingView. Pine can't read files, so the data is embedded as string constants, using the
same cut()-per-piece pattern as the Scanner Days overlays (no string constant may reach an
`if` or `var` initializer).

  python generate_pattern_overlay.py CSIQ AMD CROX ...   -> htf_pattern_overlay_TEST.pine
  python generate_pattern_overlay.py --all [KB]         -> pattern_overlays/htf_patterns_<A>_<B>.pine

--all splits every flag alphabetically into scripts of at most SCRIPT_DATA chars of data: the
Scanner Days overlays were split at ~31KB each after one combined 467KB script wouldn't load.
Reviewed tickers (in htf_pattern_truth.csv) show your label with a check mark.
"""

import os
import sys

import pandas as pd

import quick_backtest_chosen_one as qb

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = os.path.join(HERE, "htf_pattern_labels.csv")
TRUTH = os.path.join(HERE, "htf_pattern_truth.csv")
OUT = os.path.join(HERE, "htf_pattern_overlay_TEST.pine")
OUT_DIR = os.path.join(HERE, "pattern_overlays")
SPLITS = os.path.join(HERE, "pattern_overlay_splits.txt")   # first ticker of each --all script
PIECE = 3000         # chars per string constant
SCRIPT_DATA = 24000  # data chars per --all script (plus ~5KB of code stays under ~30KB)

CODE = {"Green HTF": "TH", "Perfect HTF": "PH", "Red HTF": "DH", "Expanding HTF": "EH",
        "Spiky Top HTF": "SP", "Big Green Flag": "CF", "Big Perfect Flag": "PF", "Big Red Flag": "DF", "No Pattern": "NP"}


def rec(r) -> str:
    """code,maxd,maxp,endd,t0d,t0p,t1d,t1p,l0d,l0p,l1d,l1p,retrace%,slot,
    boxL,boxR,conf,boxHi,boxLo,isHL,r1bar,r1px  (dates YYMMDD)"""
    yy = lambda d: str(int(d) % 1000000) if pd.notna(d) else "0"
    px = lambda p: f"{p:.4g}" if pd.notna(p) else "0"
    return ",".join([CODE[r.pattern], yy(r.local_max_date), px(r.local_max), yy(r.struct_end),
                     yy(r.top_d0), px(r.top_p0), yy(r.top_d1), px(r.top_p1),
                     yy(r.low_d0), px(r.low_p0), yy(r.low_d1), px(r.low_p1),
                     str(round(r.retrace * 100)), str(int(r.flag_no)) + ("✓" if r.reviewed else ""),
                     yy(r.box_l), yy(r.box_r), yy(r.setup_confirmed), px(r.box_hi), px(r.box_lo),
                     "1" if r.setup_type == "HL_FLAG" else "0", yy(r.r1_source_bar), px(r.r1_price)])


def boxes(df: pd.DataFrame) -> pd.DataFrame:
    """The recorder's box: sorted start/end clicks, spanning that window's high and low."""
    m = pd.read_csv(qb.MASTER)[["ticker", "flag_no", "flag_start", "setup_confirmed", "final_flag_end",
                                "r1_source_bar", "r1_price"]]
    df = df.merge(m, on=["ticker", "flag_no"])
    df["box_l"] = df[["flag_start", "final_flag_end"]].min(axis=1)
    df["box_r"] = df[["flag_start", "final_flag_end"]].max(axis=1)
    hi, lo = [], []
    for tk, g in df.groupby("ticker", sort=False):
        b = qb.load_bars(tk)
        for r in g.itertuples():
            w = b[(b.d >= r.box_l) & (b.d <= r.box_r)]
            hi.append((r.Index, w.high.max()))
            lo.append((r.Index, w.low.min()))
    df["box_hi"] = pd.Series(dict(hi))
    df["box_lo"] = pd.Series(dict(lo))
    return df


def load(tickers=None) -> pd.DataFrame:
    """Auto-labels, with your reviewed labels (htf_pattern_truth.csv) winning where present."""
    df = pd.read_csv(LABELS)
    df["reviewed"] = False
    if os.path.exists(TRUTH):
        t = pd.read_csv(TRUTH)[["ticker", "flag_no", "truth"]]
        df = df.merge(t, on=["ticker", "flag_no"], how="left")
        df["reviewed"] = df.truth.notna()
        df["pattern"] = df.truth.fillna(df.pattern)
    # a pattern picked in the recorder (schema 4+) counts as reviewed, after the sheet's
    rp = pd.read_csv(qb.MASTER)
    if "pattern_recorded" in rp:
        df = df.merge(rp[["ticker", "flag_no", "pattern_recorded"]], on=["ticker", "flag_no"], how="left")
        df["reviewed"] |= df.pattern_recorded.notna()
        df["pattern"] = df.truth.fillna(df.pattern_recorded).fillna(df.pattern) if "truth" in df else df.pattern_recorded.fillna(df.pattern)
    df = df[df.pattern.isin(CODE)]
    if tickers:
        df = df[df.ticker.isin(tickers)]
    return boxes(df.reset_index(drop=True))


def blob_of(df: pd.DataFrame) -> list:
    """One ';TICKER:rec/rec/...' string per ticker, alphabetical."""
    return [";" + tk + ":" + "/".join(rec(r) for r in g.itertuples()) for tk, g in df.groupby("ticker")]


def build(parts: list, title: str) -> str:
    # split on ticker boundaries only, so cut() never sees half a ticker
    pieces, cur = [], ""
    for part in parts:
        if len(cur) + len(part) > PIECE and cur:
            pieces.append(cur)
            cur = ""
        cur += part
    pieces.append(cur)
    tickers = [x[1:x.index(":")] for x in parts]
    consts = "\n".join(f'D{i} = "{p}"' for i, p in enumerate(pieces))
    cuts = "\n".join(f"s{i} = cut(D{i}, key)" for i in range(len(pieces)))
    seg = " + ".join(f"s{i}" for i in range(len(pieces)))

    pine = f'''//@version=6
// {title} -- GENERATED by generate_pattern_overlay.py; edit that, not this.
// Auto-labels from htf_pattern_labeler.py, {len(tickers)} tickers {tickers[0]}..{tickers[-1]}; a check mark = you reviewed it.
// Per flag: dotted line = local max, top/bottom fitted lines (green = rising, red = falling),
// label on the box top = slot + pattern (+ share of the pole given back, optional) (HTF vs Flag cut is {40}%).
// Boxes, confirm line, slot number and R1 are drawn exactly like the Flag Recorder's.
indicator("{title}", overlay = true, max_lines_count = 500, max_labels_count = 500, max_boxes_count = 500)

boxPad   = input.float(1.0, "Box padding %", minval = 0.0, maxval = 10.0)
showFits = input.bool(true, "Show fitted top/bottom lines")
showMax  = input.bool(true, "Show local max line")
showPole = input.bool(false, "Show % of pole given back", tooltip = "How much of the run-up the pullback gave back. Under 40% = HTF, 40%+ = Flag. Turn on to see why a flag landed in HTF vs Flag.")

{consts}

cut(string src, string k) =>
    p = str.pos(src, k)
    rest = na(p) ? "" : str.substring(src, p + str.length(k))
    q = str.pos(rest, ";")
    na(q) ? rest : str.substring(rest, 0, q)

key = ";" + syminfo.ticker + ":"
{cuts}
seg = {seg}

var string[] recs = array.new<string>()
var bool parsed = false
while not parsed
    parsed := true
    parts = str.split(seg, "/")
    j = 0
    while j < array.size(parts)
        array.push(recs, array.get(parts, j))
        j += 1

// YYMMDD -> bar time (daily bars stamp at the session open; xloc.bar_time tolerates the offset)
t(string s) =>
    v = int(str.tonumber(s))
    y = 2000 + int(math.floor(v / 10000))
    m = int(math.floor(v / 100)) % 100
    timestamp(syminfo.timezone, y, m, v % 100, 9, 30)

name(string c) =>
    c == "TH" ? "Green" : c == "PH" ? "Perfect" : c == "DH" ? "Red" : c == "EH" ? "Expanding" : c == "SP" ? "Spiky Top" : c == "CF" ? "Big Green" : c == "PF" ? "Big Perfect" : c == "NP" ? "Null" : "Big Red"

lineCol(float p0, float p1) => p1 > p0 ? color.green : color.red

if barstate.islast
    i = 0
    while i < array.size(recs)
        f = str.split(array.get(recs, i), ",")
        if array.size(f) >= 22
            // --- the recorder's own drawing ---
            t0 = t(array.get(f, 14))
            t1 = t(array.get(f, 15))
            tc = t(array.get(f, 16))
            hi = str.tonumber(array.get(f, 17))
            lo = str.tonumber(array.get(f, 18))
            pad = (hi - lo) * boxPad / 100.0
            col = array.get(f, 19) == "1" ? color.green : color.red
            box.new(left = t0, top = hi + pad, right = t1, bottom = lo - pad, xloc = xloc.bar_time, border_color = color.new(col, 100), border_width = 1, bgcolor = color.new(col, 90))
            line.new(x1 = tc, y1 = lo - pad, x2 = tc, y2 = hi + pad, xloc = xloc.bar_time, color = color.new(col, 50), width = 1, style = line.style_dashed)
            // slot number + auto-label share the recorder's label on the box's top edge
            txt = array.get(f, 13) + " " + name(array.get(f, 0)) + (showPole ? "\\n" + array.get(f, 12) + "% of pole" : "")
            label.new(x = int((t0 + t1) / 2), y = hi + pad, text = txt, xloc = xloc.bar_time, yloc = yloc.price, style = label.style_label_down, color = color.new(col, 30), textcolor = color.white, size = size.small)
            wanted = t1 + (t1 - t0)
            extEnd = wanted > time ? time : wanted
            if array.get(f, 20) != "0"
                r1 = str.tonumber(array.get(f, 21))
                line.new(x1 = t(array.get(f, 20)), y1 = r1, x2 = extEnd, y2 = r1, xloc = xloc.bar_time, color = color.orange, width = 2, style = line.style_dotted)
            // --- the auto-label ---
            if showMax
                maxP = str.tonumber(array.get(f, 2))
                line.new(t(array.get(f, 1)), maxP, t(array.get(f, 3)), maxP, xloc = xloc.bar_time, color = color.gray, style = line.style_dotted, width = 1)
            if showFits and array.get(f, 4) != "0"
                p0 = str.tonumber(array.get(f, 5))
                p1 = str.tonumber(array.get(f, 7))
                line.new(t(array.get(f, 4)), p0, t(array.get(f, 6)), p1, xloc = xloc.bar_time, color = lineCol(p0, p1), width = 2)
            if showFits and array.get(f, 8) != "0"
                q0 = str.tonumber(array.get(f, 9))
                q1 = str.tonumber(array.get(f, 11))
                line.new(t(array.get(f, 8)), q0, t(array.get(f, 10)), q1, xloc = xloc.bar_time, color = lineCol(q0, q1), width = 2)
        i += 1
'''
    return pine


def main():
    args = [a.upper() for a in sys.argv[1:]]
    if args and args[0] == "--ALL":
        # optional size per script in KB of data, e.g. --all 100 (default SCRIPT_DATA)
        limit = int(float(args[1]) * 1000) if len(args) > 1 else SCRIPT_DATA
        df = load()
        os.makedirs(OUT_DIR, exist_ok=True)
        for f in os.listdir(OUT_DIR):
            if f.endswith(".pine"):
                os.remove(os.path.join(OUT_DIR, f))
        # Split points are pinned in SPLITS so script names stay put across regenerations
        # (otherwise AMKR silently moves to another script and stops drawing). A new ticker
        # joins the script whose range it falls in; only a script over the limit is re-split.
        starts = open(SPLITS).read().split() if os.path.exists(SPLITS) else []
        parts = blob_of(df)
        tk = lambda x: x[1:x.index(":")]
        groups = []
        for part in parts:
            if not groups or (starts and any(tk(groups[-1][0]) < st <= tk(part) for st in starts))                     or (not starts and sum(map(len, groups[-1])) + len(part) > limit):
                groups.append([])
            groups[-1].append(part)
        out = []
        for g in groups:                      # re-split only a script that outgrew the limit
            cur = []
            for part in g:
                if cur and sum(map(len, cur)) + len(part) > limit * 1.15:
                    out.append(cur)
                    cur = []
                cur.append(part)
            out.append(cur)
        groups = out
        with open(SPLITS, "w") as fh:
            fh.write("\n".join(tk(g[0]) for g in groups) + "\n")
        for g in groups:
            a, b = g[0][1:g[0].index(":")], g[-1][1:g[-1].index(":")]
            path = os.path.join(OUT_DIR, f"htf_patterns_{a}_{b}.pine")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(build(g, f"HTF Patterns {a}-{b}"))
            print(f"{a:>6s}-{b:<6s} {len(g):3d} tickers  {os.path.getsize(path) / 1000:5.1f} KB  {os.path.basename(path)}")
        print(f"{len(df)} flags, {df.ticker.nunique()} tickers, {int(df.reviewed.sum())} reviewed -> {OUT_DIR}")
        return
    df = load(args)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(build(blob_of(df), "HTF Pattern Labels (TEST)"))
    print(f"{len(df)} flags, {df.ticker.nunique()} tickers -> {OUT}")


if __name__ == "__main__":
    main()
