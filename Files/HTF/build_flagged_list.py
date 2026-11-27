"""
Excel list of only the tickers you've flagged, in the same order and columns as the HTF list
(htf_scanner_master_by_ticker.csv), plus every recorded flag with its dates.

  python build_flagged_list.py   -> Files/HTF/htf_flagged_tickers.xlsx

Sheets: Flagged tickers (one row per ticker), All flags (one row per flag), Skipped (tickers
inside the range you've worked through that have no export).
"""

import os

import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
AB = os.path.join(HERE, "Advanced Backtesting")
LIST = os.path.join(HERE, "htf_scanner_master_by_ticker.csv")
MASTER = os.path.join(AB, "htf_annotations_master.csv")
LABELS = os.path.join(AB, "htf_pattern_labels.csv")
TRUTH = os.path.join(AB, "htf_pattern_truth.csv")
OUT = os.path.join(HERE, "htf_flagged_tickers.xlsx")

ymd = lambda s: pd.to_datetime(s.astype("Int64").astype(str), format="%Y%m%d", errors="coerce")


def main():
    lst = pd.read_csv(LIST)
    lst.insert(0, "list_row", range(2, len(lst) + 2))          # its row in the HTF list in Excel
    m = pd.read_csv(MASTER)
    # Exports carry the chart symbol; delisted names sit in the list as e.g. AGN.2^15 / CSH.1^16.
    by_chart = lst.drop_duplicates("chart_symbol").set_index("chart_symbol").ticker
    known = set(lst.ticker)
    m["list_ticker"] = [t if t in known else by_chart.get(t, t) for t in m.ticker]
    if os.path.exists(LABELS):
        lab = pd.read_csv(LABELS)[["ticker", "flag_no", "pattern"]].rename(columns={"pattern": "auto_pattern"})
        m = m.merge(lab, on=["ticker", "flag_no"], how="left")
    if os.path.exists(TRUTH):
        t = pd.read_csv(TRUTH).rename(columns={"truth": "reviewed_pattern", "reviewed": "pattern_reviewed_on"})
        m = m.merge(t, on=["ticker", "flag_no"], how="left")

    # --- All flags ---
    f = m.merge(lst[["ticker", "list_row"]].rename(columns={"ticker": "list_ticker"}), on="list_ticker", how="left")
    for c in ["flag_start", "setup_confirmed", "final_flag_end", "r1_effective", "r1_first_cross"]:
        f[c] = ymd(f[c])
    f["setup_type"] = f.setup_type.map({"HL_FLAG": "Green (higher low)", "LL_RECLAIM": "Red (lower low)"}).fillna(f.setup_type)
    cols = ["list_row", "ticker", "flag_no", "setup_type", "flag_start", "setup_confirmed", "final_flag_end",
            "r1_price", "r1_effective", "r1_first_cross", "auto_pattern", "reviewed_pattern", "pattern_reviewed_on"]
    flags = f[[c for c in cols if c in f]].sort_values(["list_row", "flag_no"])

    # --- Flagged tickers ---
    g = f.groupby("list_ticker").agg(
        flags=("flag_no", "size"),
        green_HL=("setup_type", lambda s: (s.str.startswith("Green")).sum()),
        red_LL=("setup_type", lambda s: (s.str.startswith("Red")).sum()),
        first_flag=("setup_confirmed", "min"),
        last_flag=("setup_confirmed", "max"),
        flag_dates=("setup_confirmed", lambda s: ", ".join(d.strftime("%Y-%m-%d") for d in sorted(s.dropna()))),
        patterns_reviewed=("reviewed_pattern", lambda s: "Y" if s.notna().all() else ("partial" if s.notna().any() else "")),
    ).reset_index().rename(columns={"list_ticker": "ticker"})
    keep = ["list_row", "ticker", "chart_symbol", "former_symbols", "mktcap_bucket", "n_streaks",
            "first_seen", "last_seen", "windows_per_streak", "total_flagpoles"]
    tick = lst[keep].merge(g, on="ticker").sort_values("list_row")
    for c in ["first_seen", "last_seen"]:
        tick[c] = pd.to_datetime(tick[c], errors="coerce")

    # --- Skipped: in the worked-through range but never exported ---
    last = tick.list_row.max()
    skipped = lst[(lst.list_row <= last) & ~lst.ticker.isin(g.ticker)][keep]

    with pd.ExcelWriter(OUT, engine="openpyxl", datetime_format="yyyy-mm-dd") as xw:
        for name, df in [("Flagged tickers", tick), ("All flags", flags), ("Skipped", skipped)]:
            df.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            ws.freeze_panes = "C2"
            ws.auto_filter.ref = ws.dimensions
            for cell in ws[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="305496")
            for i, col in enumerate(df.columns, start=1):
                width = max(len(str(col)), *(len(str(v)) for v in df[col].head(300))) if len(df) else len(col)
                ws.column_dimensions[get_column_letter(i)].width = min(60, max(9, width + 2))

    print(f"{len(tick)} flagged tickers, {len(flags)} flags, {len(skipped)} skipped "
          f"(through list row {last}, {tick.ticker.iloc[-1]}) -> {OUT}")


if __name__ == "__main__":
    main()
