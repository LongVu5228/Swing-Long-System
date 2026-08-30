"""
Load the EP V5 master event universe (Files/EP/EP V5.xlsx, sheet "Data") into a clean,
canonical DataFrame and cache it as Parquet.

Confirmed 2026-08-30 (see Section 96 of the frozen V1 spec): EP V5 is now the master
ticker/event source for the backtest, superseding the Benzinga candidate list / EP V4.

gap_pct and adr14 are stored in EP V5 as whole-number percentages (e.g. 6.19 means
6.19%), not decimals -- confirmed by inspecting sample rows. This loader converts both
to decimal fractions (0.0619) so the rest of the engine works in one consistent unit.
"""

import os

import openpyxl
import pandas as pd

from . import config

# Columns essential to V1/V2, renamed to snake_case. Every other EP V5 column is kept
# as an attached feature (Section 62) under its original header, just slugified.
_ESSENTIAL = {
    "Unique": "event_id",
    "reaction_date": "reaction_date",
    "ticker": "ticker",
    "Chart Pattern": "chart_pattern",
    "gap_pct": "gap_pct",
    "adr14": "adr14",
    "pre_gap_market_cap": "pre_gap_market_cap",
}


def _slugify(header: str) -> str:
    if header in _ESSENTIAL:
        return _ESSENTIAL[header]
    text = str(header).strip().replace("%", " pct ")
    out = []
    for ch in text:
        if ch.isalnum():
            out.append(ch.lower())
        elif ch in " -/?":
            out.append("_")
        # drop other punctuation (parens etc.)
    slug = "".join(out)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def load_ep_v5(refresh: bool = False) -> pd.DataFrame:
    if not refresh and os.path.exists(config.EVENTS_PARQUET):
        return pd.read_parquet(config.EVENTS_PARQUET)

    wb = openpyxl.load_workbook(config.EP_V5_XLSX, read_only=True, data_only=True)
    ws = wb[config.EP_V5_SHEET]
    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter)
    slugged = [_slugify(h) for h in header]
    if len(set(slugged)) != len(slugged):
        dupes = {c for c in slugged if slugged.count(c) > 1}
        raise ValueError(f"Slugified EP V5 headers collide: {dupes}")

    records = [dict(zip(slugged, row)) for row in rows_iter]
    df = pd.DataFrame.from_records(records)

    # Excel formulas that couldn't resolve show up as the literal string "N/A" --
    # normalize those to real nulls before any type coercion.
    df = df.replace({"N/A": None, "n/a": None, "": None})

    df["reaction_date"] = pd.to_datetime(df["reaction_date"]).dt.date
    df["ticker"] = df["ticker"].astype(str).str.strip()
    df["chart_pattern"] = df["chart_pattern"].astype(str).str.strip()

    # EP V5 stores gap_pct/adr14 as whole-number percentages -- normalize to decimals.
    for col in ("gap_pct", "adr14"):
        df[col] = pd.to_numeric(df[col], errors="coerce") / 100.0
    df["pre_gap_market_cap"] = pd.to_numeric(df["pre_gap_market_cap"], errors="coerce")

    already_typed = {"reaction_date", "ticker", "chart_pattern", "gap_pct", "adr14", "pre_gap_market_cap"}
    for col in df.columns:
        if col in already_typed or df[col].dtype != object:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        # Only adopt the numeric version if it didn't turn any real (non-null) value
        # into NaN -- otherwise this is a genuinely mixed/text column, keep it as text.
        lost = numeric.isna() & df[col].notna()
        if not lost.any():
            df[col] = numeric
        else:
            df[col] = df[col].astype("string")

    df = df.dropna(subset=["reaction_date", "ticker"]).reset_index(drop=True)

    os.makedirs(config.CACHE_DIR, exist_ok=True)
    df.to_parquet(config.EVENTS_PARQUET, index=False)
    return df


if __name__ == "__main__":
    events = load_ep_v5(refresh=True)
    print(f"{len(events)} events, {events['ticker'].nunique()} unique tickers")
    print(f"date range: {events['reaction_date'].min()} .. {events['reaction_date'].max()}")
    print(f"chart_pattern counts:\n{events['chart_pattern'].value_counts()}")
    print(f"\nsample adr14/gap_pct (decimal):\n{events[['ticker', 'reaction_date', 'gap_pct', 'adr14']].head()}")
    print(f"\ncached to {config.EVENTS_PARQUET}")
