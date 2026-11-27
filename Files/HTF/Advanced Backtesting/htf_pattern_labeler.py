"""
Auto-label every annotated flag with the user's whiteboard taxonomy (2026-11-05), as a
first pass for the user to correct by eye -- not ground truth.

                 both lines rising   red top / green bottom   both lines falling
  HTF            Green HTF           Perfect HTF              Red HTF
  Flag           Big Green Flag          Big Perfect Flag             Big Red Flag
  + Spiky Top HTF: highs inside the flag keep breaking the local max (normally skipped).

A Flag is judged by where its low sits: if price keeps making lower lows into the back 60% of
the flag it is a Big Red Flag, and the climb off that late low is just its breakout. A low near
the start with the base building to the right is Green/Perfect (AMD + AA..ABEO reviews).

User corrections live in htf_pattern_truth.csv; every run scores against them.

HTF vs Flag is the user's eye ("tucked under the high" vs a "big" V pullback); proxied here
by how much of the pole the flag gives back (RETRACE_FLAG), the main thing to calibrate.

Click geometry (checked on real exports): flag_start is the flag's FIRST LOW, not the top --
the local max sits in the bars just before it, and R1 is the line of least resistance under
that max. The structure is read from flag_start to the bar before R1 is first crossed.
"""

import os

import numpy as np
import pandas as pd

import quick_backtest_chosen_one as qb

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "htf_pattern_labels.csv")
TRUTH = os.path.join(HERE, "htf_pattern_truth.csv")

TOP_LOOKBACK = 15      # bars before flag_start searched for the local max (pole top)
BASE_LOOKBACK = 60     # bars before the top searched for the pole's base
RETRACE_FLAG = 0.40    # pullback giving back >= this share of the pole = Flag, else HTF
SPIKY_BREAKS = 2       # swing highs above the local max needed for a Spiky Top: one poke
                       # above it is still an HTF under that max (AMD 2009-04, AVAV 2018-07)
DOWNTREND_LOW_POS = 0.40  # Flag whose lowest low sits 40%+ of the way in = Big Red Flag: it starts
                          # high and goes lower to the right. Low near the start = a base off the
                          # first low = Green/Perfect. Retuned 2026-11-06 on 73 reviewed flags
                          # (was 0.75 + a higher-low count): 59 -> 63 match, flat 0.35-0.50.
GREEN_FLAG_HL = 0      # higher lows after the bottom a Flag needs to be Green/Perfect (0 = off;
                       # a low at bar 0 has no room for them, ABEO 2015/2018)


def pivots(s: pd.Series, kind: str, k: int = 1) -> pd.Series:
    """Swing highs/lows: a bar beating its k neighbours each side."""
    r = s.rolling(2 * k + 1, center=True)
    ext = r.max() if kind == "high" else r.min()
    return s[(s == ext)].dropna()


def slope(pts: pd.Series, raw: pd.Series = None):
    """Fitted slope of pivot prices vs bar index, as % of mean price per bar. Short flags
    with fewer than two swing points fall back to fitting every bar (`raw`)."""
    if len(pts) < 2:
        if raw is None or len(raw) < 2:
            return np.nan, None
        pts = raw
    x = np.asarray(pts.index, float)
    a, c = np.polyfit(x, pts.values, 1)
    s = a / pts.mean() * 100
    # Equal highs fit to a slope of exactly 0, but polyfit returns float noise (+1e-17) that
    # flipped flat-topped flags to Green. Flat = not rising (Perfect), and the recorder's Pine
    # port, which sums exactly, must agree (AGEN 6, BCRX 21, CDE 15).
    if abs(s) < 1e-9:
        s = 0.0
    return s, (x[0], a * x[0] + c, x[-1], a * x[-1] + c)


def label_flag(b: pd.DataFrame, f) -> dict:
    idx = lambda d: b.index[b.d >= d][0] if (b.d >= d).any() else None
    s = idx(f.flag_start)
    stop_d = f.r1_first_cross if pd.notna(f.r1_first_cross) else max(f.final_flag_end, f.setup_confirmed)
    e = idx(stop_d)
    if s is None or e is None:
        return {"pattern": "NO_BARS"}
    e = max(s + 2, e - 1)                       # structure ends the bar before the breakout
    w = b.iloc[s:e + 1]
    c = min(e, max(s, idx(f.setup_confirmed) or s))   # confirm can land after the cutoff
    pre = b.iloc[max(0, s - TOP_LOOKBACK):s + 1]
    pre_top = pre.high.max()
    # The local max can sit just inside the box (flag_start is a low, and the top can print a
    # bar or two after it -- AMD 2009-04). It is a Spiky Top only when highs keep breaking the
    # prior top AND the highest high comes late, i.e. the "flag" is still trending up.
    early = b.iloc[s:c + 1]
    win_top_i = early.high.idxmax()
    breaks = int((pivots(w.high, "high") > pre_top).sum())
    late = (win_top_i - s) / max(1, c - s) > 0.5
    spiky = breaks >= SPIKY_BREAKS and late
    top_i = pre.high.idxmax()
    base = b.iloc[max(0, top_i - BASE_LOOKBACK):top_i + 1].low.min()
    retrace = (pre_top - w.low.min()) / (pre_top - base) if pre_top > base else np.nan
    # ...but only for an HTF: a big-V Flag's base can climb past the old top (AMD 2020-03)
    # and its local max is still the top before the pullback.
    if retrace < RETRACE_FLAG and b.high[win_top_i] > pre_top and not spiky:
        top_i = win_top_i
    top = b.high[top_i]
    if s < top_i < e - 1:                       # structure is read from the top onward
        w = b.iloc[top_i:e + 1]
    lo_i = w.low.idxmin()
    depth = (1 - w.low.min() / top) * 100
    low_pos = (lo_i - s) / max(1, e - s)

    out = dict(local_max=round(top, 4), local_max_date=int(b.d[top_i]), struct_end=int(b.d[e]),
               retrace=round(retrace, 3),
               depth_pct=round(depth, 1), flag_bars=e - s + 1, low_pos=round(low_pos, 2))
    family = "Flag" if retrace >= RETRACE_FLAG else "HTF"

    if family == "Flag":
        seg = b.iloc[top_i:e + 1]               # a Flag's lines span the whole pullback
        post = b.iloc[lo_i:e + 1]               # after the V bottom
        post_lows = pivots(post.low, "low")
        higher_lows = int((np.diff(post_lows.values) > 0).sum()) if len(post_lows) > 1 else 0
        out["post_low_HL"] = higher_lows
        if low_pos >= DOWNTREND_LOW_POS or higher_lows < GREEN_FLAG_HL:
            hs, hl = slope(pivots(seg.high, "high"), seg.high)
            ls, ll = slope(pivots(seg.low, "low"), seg.low)
            pattern = "Big Red Flag"
        else:
            hs, hl = slope(pivots(post.high, "high"), post.high)
            if hl is None:
                hs, hl = slope(pivots(seg.high, "high"), seg.high)
            ls, ll = slope(post_lows, post.low)
            pattern = "Big Green Flag" if (hs or 0) > 0 else "Big Perfect Flag"
    else:
        hs, hl = slope(pivots(w.high, "high"), w.high)
        ls, ll = slope(pivots(w.low, "low"), w.low)
        if spiky:
            pattern = "Spiky Top HTF"
        elif hl is None or ll is None:
            pattern = "HTF (too short)"
        elif hs > 0 and ls > 0:
            pattern = "Green HTF"
        elif hs <= 0 and ls > 0:
            pattern = "Perfect HTF"
        elif hs <= 0 and ls <= 0:
            pattern = "Red HTF"
        else:
            pattern = "Expanding HTF"  # rising top over falling lows (user kept it, 2026-11-05)

    out.update(pattern=pattern, family=family,
               top_slope=round(hs, 3) if pd.notna(hs) else None, low_slope=round(ls, 3) if pd.notna(ls) else None)
    # fitted line endpoints as (date, price) for the Pine overlay
    for name, ln in (("top", hl), ("low", ll)):
        if ln is not None:
            x0, y0, x1, y1 = ln
            out.update({f"{name}_d0": int(b.d[int(x0)]), f"{name}_p0": round(y0, 4),
                        f"{name}_d1": int(b.d[int(x1)]), f"{name}_p1": round(y1, 4)})
    return out


def main():
    m = qb.read_master()
    m = m[~m.ticker.isin(qb.EXCLUDE)]
    rows = []
    for tk, g in m.groupby("ticker"):
        b = qb.load_bars(tk)
        for f in g.itertuples():
            r = {"pattern": "NO_BARS"} if b is None else label_flag(b, f)
            rows.append({"ticker": tk, "flag_no": f.flag_no, "setup_type": f.setup_type, **r})
    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"{len(df)} flags -> {OUT}\n")
    print(pd.crosstab(df.pattern, df.setup_type, margins=True).to_string())
    print("\nretrace quantiles:", df.retrace.quantile([.1, .25, .5, .75, .9]).round(2).to_dict())

    t = pd.read_csv(TRUTH)[["ticker", "flag_no", "truth"]] if os.path.exists(TRUTH) else pd.DataFrame(columns=["ticker", "flag_no", "truth"])
    if "pattern_recorded" in m:   # patterns picked in the recorder (schema 4+) are truth too
        # ...but not ones left on Auto (schema 5): those ARE this labeler, scoring them is circular
        mine = m.pattern_recorded.notna()
        if "pattern_source" in m:
            mine &= m.pattern_source.ne("auto")
        rec = m[mine][["ticker", "flag_no", "pattern_recorded"]].rename(columns={"pattern_recorded": "truth"})
        t = pd.concat([t, rec[~rec.set_index(["ticker", "flag_no"]).index.isin(t.set_index(["ticker", "flag_no"]).index)]])
    if len(t):
        t = t.merge(df[["ticker", "flag_no", "pattern"]], on=["ticker", "flag_no"])
        hit = t.truth == t.pattern
        print(f"\nvs your corrections: {hit.sum()}/{len(t)} = {hit.mean():.0%} match")
        miss = t[~hit]
        if len(miss):
            print(miss[["ticker", "flag_no", "truth", "pattern"]].to_string(index=False))


if __name__ == "__main__":
    main()
