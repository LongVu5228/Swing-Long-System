# Episodic Pivot V4 — Final Deep Analysis & Verification Manual
**Full-history research pass (2011–2026) — final feature-selection analysis before entry/exit backtesting**

**Primary workbook:** `EP V4.xlsx`  
**Analysis cutoff inferred from workbook:** 2026-08-21  
**Primary outcome:** maximum future upside (MFE-like high %) measured from the gap-day open, at 1M / 3M / 6M horizons  
**Important:** these are *opportunity* statistics, not realized trading returns.

**Revision — 2026-08-23:** the workbook `Era` formula has been corrected to use the **actual reaction year** rather than fiscal year. The regime statistics in this report already derived year/era directly from `reaction_date`, so this workbook correction does **not** change the reported regime tables, regressions, or conclusions; it only resolves the prior workbook-field QC issue.

---

## Executive conclusions

1. **The EP phenomenon is not a post-COVID artifact.** V4’s full-history 6M baseline is 20.85% reaching +50% and 5.99% reaching +100%, almost identical to V3’s 20.77% / 6.33% despite adding roughly a decade of older data. What changes dramatically is *which years are favorable*, not whether EPs existed before COVID.
2. **Market regime is enormous.** Mature 6M +50% rates range from 4.6% in 2014 to 45.3% in 2020; 2021–2022 were weak again. Any execution backtest that pools years without at least reporting regime/year results will hide a major source of variance.
3. **ADR remains the foundational pre-entry feature.** The relationship is monotonic enough to be hard to dismiss: 6M +50% rises from 8.5% at ADR 2–3% to 41.9% at ADR 10%+; +100% rises from 0.9% to 17.7%. ADR ≥5% captures 60.7% of all 6M doubles while representing only 23.6% of mature events.
4. **Turnover matters; absolute dollar volume mostly does not.** Turnover ≥2% produces 31.3% +50% and 12.8% +100% at 6M. Absolute 30D dollar-volume buckets are weak/non-monotonic, supporting the idea that dollar volume is chiefly an eligibility/liquidity constraint while *activity relative to company size* is more informative.
5. **Intraday price acceptance is a major confirmation variable.** By 10 minutes, green candles materially outperform red candles; within ADR ≥5%, 10M Green reaches +50% 43.6% of the time versus 31.4% for 10M Red. At 60 minutes the separation is 44.8% vs 30.7%.
6. **Volume is strongest when paired with acceptance.** At 60M, Green + ≥2.5x ADV reaches +50% 33.9% and +100% 14.2%, while Red + ≥2.5x reaches only 18.8% / 4.8%. The same principle appears at 10M: ADR ≥5% + Green + ≥0.45x ADV reaches 48.2% +50% and 22.9% +100%.
7. **Deep drawdown and large gap remain powerful descriptive phenotypes.** ≥70% below ATH: 38.3% +50%, 14.8% +100%. ≥85% below ATH: 47.9% / 22.5% (N=169). Gap ≥20%: 35.9% / 17.0%. But deep ATH and small market cap lose some independent importance after controlling ADR/turnover/gap/era; they should be treated as enrichment variables rather than blindly mandatory filters.
8. **Revenue surprise and “Both Big Beats” validate; “Both Miss” does not validate as timeless.** Revenue surprise ≥15% remains independently useful after technical controls. Both Big Beats remains useful. The V3 “Both Miss” anomaly is mostly a 2021+ effect and is not independently significant over full history.
9. **EPS/revenue state contains real information, but needs data-quality caution.** EPS loss/transition states and revenue growth ≥35% remain strongly associated after technical controls, yet EPS is vulnerable to GAAP/non-GAAP and near-zero denominator issues. Treat these as candidate features for backtesting, not unquestioned truth.
10. **Exit design is at least as important as selection.** At 6M, 20.85% of EPs trade +50% at some point, but only 10.80% are still +50% at the 6M close. Median MFE-to-close giveback is 21.0 percentage points. This dataset says “there was a large move” far more often than “buy and hold six months realized it.”
11. **Workbook Era QC is now resolved.** Column H `Era` has been updated to reference the **actual reaction year**. The report itself already derived market year/era from column A `reaction_date`, so this formula correction does not change any regime statistics or conclusions; column H can now be used for the same era pivots, provided its bucket boundaries match the reaction-era definition in §3.2.
12. **IPO-age analysis has a larger QC problem than V3:** 135 unique events have invalid IPO dates (1900 placeholders or IPO date after event date). They are excluded from IPO-age statistics in this report.

---

## 1. Audit, definitions, and reproducibility

### 1.1 Workbook audit
| Item | Result |
| :--- | ---: |
| Raw rows | 9,605 |
| Unique ticker + reaction-date events | 9,599 |
| Unique tickers | 2,150 |
| Duplicate event keys | 3 |
| Excess duplicate rows | 6 |
| Invalid IPO-date events | 135 |
| Workbook `Era` formula status | Corrected to reaction year |
| Actual data columns | 115 columns (A:DK) |

The primary technical/outcome analysis deduplicates on **Ticker + reaction_date**, because multiple fiscal periods reported on the same market reaction date are one tradable market event. The three duplicate event keys are: **HAIN 2017-06-22 (4 rows), SMCI 2025-02-26 (2 rows), PACS 2025-11-20 (3 rows)**. For fundamental analysis, those duplicate event keys are excluded rather than arbitrarily choosing one fiscal row.

### 1.2 Strict maturity
The workbook cutoff is 2026-08-21. A future horizon is included only if the full calendar horizon had elapsed. This prevents recent rows with incomplete future windows from being treated as failures.
| Horizon | Maturity cutoff | Mature raw rows | Mature unique events |
| :--- | :--- | ---: | ---: |
| 1M | 2026-07-21 | 9,199 | 9,193 |
| 3M | 2026-05-21 | 9,129 | 9,123 |
| 6M | 2026-02-21 | 8,615 | 8,609 |

### 1.3 Outcome definition
- **1M High %** = column CM; **3M High %** = CT; **6M High %** = DB.
- The denominator is the **gap-day open**. Therefore a +50% event means the stock traded at least 50% above its gap-day open at some point before the horizon cutoff.
- This is an MFE-like opportunity measure. It does **not** prove any entry was achievable, that the position survived a stop, or that +50% was realized.
- Close-performance fields (CQ/CX/DF) are analyzed separately to show how much of the path-dependent opportunity remains at the horizon close.

### 1.4 Statistical tools
- **Rates and counts:** every important percentage is reported with its numerator and denominator where practical.
- **Wilson 95% confidence intervals:** used for binary rates such as +50% and +100%.
- **Cramér’s V:** descriptive association between categorical factor buckets and the seven-bin future-upside distribution. It is not causality or predictive accuracy.
- **Spearman correlation:** monotonic rank association for continuous variables and redundancy checks.
- **Logistic regression:** cluster-robust standard errors by ticker, with reaction-era controls. These models answer whether a feature adds information conditional on other included features; they do not establish a tradable strategy.

### 1.5 Workbook `Era` QC — resolved
The workbook `Era` field has now been corrected to reference the **actual reaction year**. In the earlier workbook version used during the first audit, column H had followed `fiscal_year`, producing 1,076 mismatches versus reaction-date era; that issue is now fixed and the old mismatch count is **not applicable to the current workbook**. Importantly, all market-regime analysis in this report was already derived independently from column A `reaction_date`, so the correction does **not** require changing the reported year/era rates, Cramér’s V values for Reaction Era, or regression controls.

The following formulas remain the independent audit definition that column H should reproduce:
```excel
Reaction Year: =YEAR(A2)
Reaction Era: =IFS(YEAR(A2)<=2016,"01 | 2011-2016",YEAR(A2)<=2019,"02 | 2017-2019",YEAR(A2)=2020,"03 | 2020",YEAR(A2)<=2022,"04 | 2021-2022",YEAR(A2)<=2025,"05 | 2023-2025",TRUE,"06 | 2026")
```

---

## 2. Baseline outcomes — V4 versus V3

| Horizon | Mature N | 30%+ | 50%+ | 100%+ | Median MFE | Mean MFE | 95% CI 50%+ | 95% CI 100%+ |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1M | 9,193 | 818 / 8.90% | 262 / 2.85% | 32 / 0.35% | 9.21% | 13.27% | 2.53–3.21% | 0.25–0.49% |
| 3M | 9,123 | 2,351 / 25.77% | 1,001 / 10.97% | 205 / 2.25% | 16.32% | 24.46% | 10.35–11.63% | 1.96–2.57% |
| 6M | 8,609 | 3,492 / 40.56% | 1,795 / 20.85% | 516 / 5.99% | 23.42% | 36.50% | 20.01–21.72% | 5.51–6.52% |

**Replication check against V3:**
| Horizon | V3 50%+ | V4 50%+ | Δ | V3 100%+ | V4 100%+ | Δ |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1M | 3.16% | 2.85% | -0.31 pp | 0.36% | 0.35% | -0.01 pp |
| 3M | 11.78% | 10.97% | -0.81 pp | 2.49% | 2.25% | -0.24 pp |
| 6M | 20.77% | 20.85% | +0.08 pp | 6.33% | 5.99% | -0.34 pp |

The 6M baseline barely moved: **20.77% → 20.85% for +50%**, while +100% moved **6.33% → 5.99%**. That is important evidence against the idea that the entire EP phenomenon only exists in the post-COVID sample. The *average* opportunity distribution survives; the regime composition changes substantially.

### 2.1 MFE versus horizon-close returns
| Horizon | Median MFE | Median close return | Close >0 | MFE 50%+ | Close 50%+ | MFE 100%+ | Close 100%+ | Median giveback |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1M | 9.21% | 0.99% | 53.4% | 2.85% | 1.24% | 0.35% | 0.17% | 8.25% |
| 3M | 16.32% | 2.12% | 53.8% | 10.97% | 5.54% | 2.25% | 1.02% | 14.64% |
| 6M | 23.42% | 3.24% | 54.4% | 20.85% | 10.80% | 5.99% | 3.16% | 21.00% |

At 6M, among the **1,795** events that traded +50% or more, **17.5%** finished below +20% and **9.2%** actually finished negative. Among the **516** doubles, **18.2%** finished below +50%. This is direct evidence that entry/exit rules will dominate realized expectancy even if selection is good.

---

## 3. Market regime: EPs are timeless enough, but not regime-invariant

### 3.1 Reaction-year table (6M mature)
| Reaction year | N | 50%+ | 100%+ | Median MFE | Note |
| :--- | ---: | ---: | ---: | ---: | :--- |
| 2011 | 5 | 0 / 0.00% | 0 / 0.00% | 13.42% | Tiny N |
| 2012 | 105 | 10 / 9.52% | 2 / 1.90% | 20.91% |  |
| 2013 | 124 | 22 / 17.74% | 5 / 4.03% | 28.67% |  |
| 2014 | 175 | 8 / 4.57% | 0 / 0.00% | 16.17% |  |
| 2015 | 301 | 19 / 6.31% | 0 / 0.00% | 13.50% |  |
| 2016 | 392 | 71 / 18.11% | 16 / 4.08% | 25.37% |  |
| 2017 | 320 | 63 / 19.69% | 11 / 3.44% | 25.59% |  |
| 2018 | 526 | 73 / 13.88% | 13 / 2.47% | 20.66% |  |
| 2019 | 577 | 78 / 13.52% | 17 / 2.95% | 19.93% |  |
| 2020 | 827 | 375 / 45.34% | 130 / 15.72% | 45.80% |  |
| 2021 | 714 | 98 / 13.73% | 22 / 3.08% | 15.76% |  |
| 2022 | 885 | 109 / 12.32% | 21 / 2.37% | 19.01% |  |
| 2023 | 877 | 178 / 20.30% | 46 / 5.25% | 25.84% |  |
| 2024 | 1,125 | 243 / 21.60% | 72 / 6.40% | 24.16% |  |
| 2025 | 1,444 | 386 / 26.73% | 135 / 9.35% | 26.39% |  |
| 2026 | 212 | 62 / 29.25% | 26 / 12.26% | 26.27% | Partial 2026 |

The strongest year by far is 2020 (**45.34% +50%, 15.72% +100%**). But the years immediately around it show why “post-COVID only” is too simplistic: 2016–2017 were respectable, 2021–2022 were weak, and 2023–2025 improved again. The market environment—not simply chronological recency—matters.

### 3.2 Reaction-era table (6M mature)
| Reaction era | N | 30%+ | 50%+ | 100%+ | Median MFE |
| :--- | ---: | ---: | ---: | ---: | ---: |
| 01 \| 2011-2016 | 1,102 | 350 / 31.76% | 130 / 11.80% | 23 / 2.09% | 20.24% |
| 02 \| 2017-2019 | 1,423 | 512 / 35.98% | 214 / 15.04% | 41 / 2.88% | 21.59% |
| 03 \| 2020 | 827 | 568 / 68.68% | 375 / 45.34% | 130 / 15.72% | 45.80% |
| 04 \| 2021-2022 | 1,599 | 465 / 29.08% | 207 / 12.95% | 43 / 2.69% | 18.00% |
| 05 \| 2023-2025 | 3,446 | 1,501 / 43.56% | 807 / 23.42% | 253 / 7.34% | 25.47% |
| 06 \| 2026 | 212 | 96 / 45.28% | 62 / 29.25% | 26 / 12.26% | 26.27% |

Cramér’s V for **Reaction Era vs the full 6M outcome distribution = 0.121**, making regime one of the strongest non-intraday associations in the dataset. Any backtest should report performance by year/era and should not infer future expectancy solely from 2020.

---

## 4. Association ranking

Cramér’s V ranks *association*, not causal importance. Intraday candle color is inherently a later observation than pre-gap fundamentals or ADR, so the ranking must be separated by observability.
### 1M association ranking
| Rank | Factor | N | Cramér V | p-value | Levels |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 1 | Gap Day Color | 9,193 | 0.415 | 0.00e+00 | 2 |
| 2 | 60M Color | 9,193 | 0.348 | 1.17e-237 | 2 |
| 3 | 30M Color | 9,193 | 0.329 | 3.59e-211 | 2 |
| 4 | 15M Color | 9,192 | 0.306 | 3.93e-183 | 2 |
| 5 | 10M Color | 9,185 | 0.290 | 3.62e-163 | 2 |
| 6 | 5M Color | 9,109 | 0.246 | 5.51e-116 | 2 |
| 7 | ADR | 9,193 | 0.177 | 1.02e-285 | 6 |
| 8 | 1M Color | 8,599 | 0.122 | 2.13e-25 | 2 |
| 9 | ATH | 9,193 | 0.104 | 7.63e-102 | 7 |
| 10 | Dollar Turnover | 9,193 | 0.102 | 1.32e-82 | 6 |
| 11 | Day Rel Vol | 9,193 | 0.096 | 5.52e-58 | 5 |
| 12 | EPS YoY | 8,682 | 0.096 | 1.87e-72 | 9 |
| 13 | Gap | 9,193 | 0.085 | 2.70e-52 | 6 |
| 14 | Market Cap | 9,193 | 0.077 | 3.09e-49 | 7 |
| 15 | Reaction Era | 9,193 | 0.077 | 1.11e-40 | 6 |
| 16 | Year | 9,193 | 0.076 | 7.67e-27 | 16 |
| 17 | Rev YoY | 8,648 | 0.075 | 6.41e-35 | 6 |
| 18 | 60M Rel Vol | 9,193 | 0.072 | 6.67e-28 | 5 |
| 19 | Surprise Matrix | 8,613 | 0.072 | 4.20e-32 | 9 |
| 20 | EPS Surprise | 8,757 | 0.066 | 1.91e-30 | 7 |
| 21 | 30M Rel Vol | 9,193 | 0.066 | 2.16e-22 | 5 |
| 22 | Fiscal Period | 9,193 | 0.066 | 2.19e-27 | 6 |
| 23 | IPO Age | 9,058 | 0.066 | 2.55e-26 | 6 |
| 24 | Revenue Surprise | 8,758 | 0.063 | 1.52e-26 | 7 |
| 25 | 15M Rel Vol | 9,192 | 0.059 | 5.05e-16 | 5 |
| 26 | 10M Rel Vol | 9,185 | 0.057 | 8.72e-15 | 5 |
| 27 | 5M Rel Vol | 9,109 | 0.051 | 3.59e-10 | 5 |
| 28 | 1M Rel Vol | 8,599 | 0.044 | 6.59e-06 | 5 |
| 29 | Sector | 8,394 | 0.040 | 0.0021 | 9 |
| 30 | Dollar Volume | 9,193 | 0.036 | 0.0014 | 6 |
| 31 | SPY | 9,193 | 0.018 | 0.9518 | 4 |
| 32 | Release Timing | 9,193 | 0.015 | 0.9844 | 3 |

### 3M association ranking
| Rank | Factor | N | Cramér V | p-value | Levels |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 1 | Gap Day Color | 9,123 | 0.320 | 5.39e-199 | 2 |
| 2 | 60M Color | 9,123 | 0.275 | 9.58e-146 | 2 |
| 3 | 30M Color | 9,123 | 0.256 | 1.05e-125 | 2 |
| 4 | 15M Color | 9,122 | 0.240 | 6.70e-110 | 2 |
| 5 | 10M Color | 9,115 | 0.226 | 1.23e-97 | 2 |
| 6 | 5M Color | 9,039 | 0.189 | 1.04e-66 | 2 |
| 7 | ADR | 9,123 | 0.168 | 2.23e-253 | 6 |
| 8 | Dollar Turnover | 9,123 | 0.103 | 6.28e-84 | 6 |
| 9 | ATH | 9,123 | 0.102 | 2.64e-96 | 7 |
| 10 | Year | 9,123 | 0.101 | 5.25e-69 | 16 |
| 11 | EPS YoY | 8,613 | 0.101 | 7.02e-81 | 9 |
| 12 | Reaction Era | 9,123 | 0.099 | 2.14e-75 | 6 |
| 13 | 1M Color | 8,529 | 0.092 | 1.54e-13 | 2 |
| 14 | Day Rel Vol | 9,123 | 0.081 | 3.41e-37 | 5 |
| 15 | Gap | 9,123 | 0.079 | 5.36e-44 | 6 |
| 16 | Market Cap | 9,123 | 0.076 | 3.26e-46 | 7 |
| 17 | Surprise Matrix | 8,543 | 0.071 | 4.30e-30 | 9 |
| 18 | Rev YoY | 8,578 | 0.067 | 1.41e-25 | 6 |
| 19 | EPS Surprise | 8,687 | 0.064 | 1.19e-27 | 7 |
| 20 | IPO Age | 8,988 | 0.063 | 7.89e-23 | 6 |
| 21 | Fiscal Period | 9,123 | 0.063 | 3.12e-23 | 6 |
| 22 | Revenue Surprise | 8,688 | 0.060 | 1.40e-22 | 7 |
| 23 | 60M Rel Vol | 9,123 | 0.058 | 2.53e-15 | 5 |
| 24 | 30M Rel Vol | 9,123 | 0.056 | 1.80e-13 | 5 |
| 25 | 10M Rel Vol | 9,115 | 0.054 | 4.62e-12 | 5 |
| 26 | 15M Rel Vol | 9,122 | 0.053 | 1.32e-11 | 5 |
| 27 | 5M Rel Vol | 9,039 | 0.049 | 2.98e-09 | 5 |
| 28 | 1M Rel Vol | 8,529 | 0.044 | 5.77e-06 | 5 |
| 29 | Sector | 8,330 | 0.043 | 0.0001 | 9 |
| 30 | Release Timing | 9,123 | 0.036 | 0.0237 | 3 |
| 31 | Dollar Volume | 9,123 | 0.033 | 0.0139 | 6 |
| 32 | SPY | 9,123 | 0.026 | 0.4206 | 4 |

### 6M association ranking
| Rank | Factor | N | Cramér V | p-value | Levels |
| ---: | :--- | ---: | ---: | ---: | ---: |
| 1 | Gap Day Color | 8,609 | 0.267 | 2.18e-129 | 2 |
| 2 | 60M Color | 8,609 | 0.229 | 3.82e-94 | 2 |
| 3 | 30M Color | 8,609 | 0.213 | 5.39e-81 | 2 |
| 4 | 15M Color | 8,608 | 0.199 | 6.09e-71 | 2 |
| 5 | 10M Color | 8,601 | 0.186 | 1.82e-61 | 2 |
| 6 | 5M Color | 8,526 | 0.162 | 1.31e-45 | 2 |
| 7 | ADR | 8,609 | 0.148 | 1.74e-178 | 6 |
| 8 | Year | 8,609 | 0.128 | 2.94e-122 | 16 |
| 9 | Reaction Era | 8,609 | 0.121 | 2.34e-113 | 6 |
| 10 | EPS YoY | 8,116 | 0.097 | 3.16e-68 | 9 |
| 11 | Dollar Turnover | 8,609 | 0.088 | 2.23e-52 | 6 |
| 12 | 1M Color | 8,036 | 0.079 | 3.31e-09 | 2 |
| 13 | ATH | 8,609 | 0.075 | 3.25e-42 | 7 |
| 14 | Gap | 8,609 | 0.074 | 1.68e-33 | 6 |
| 15 | Surprise Matrix | 8,046 | 0.069 | 1.16e-25 | 9 |
| 16 | Market Cap | 8,609 | 0.069 | 1.79e-32 | 7 |
| 17 | Day Rel Vol | 8,609 | 0.068 | 1.31e-21 | 5 |
| 18 | EPS Surprise | 8,180 | 0.064 | 3.16e-25 | 7 |
| 19 | Revenue Surprise | 8,190 | 0.063 | 9.14e-24 | 7 |
| 20 | Rev YoY | 8,085 | 0.060 | 3.59e-17 | 6 |
| 21 | IPO Age | 8,474 | 0.058 | 1.43e-16 | 6 |
| 22 | 10M Rel Vol | 8,601 | 0.054 | 4.88e-11 | 5 |
| 23 | 15M Rel Vol | 8,608 | 0.051 | 1.34e-09 | 5 |
| 24 | 60M Rel Vol | 8,609 | 0.051 | 2.36e-09 | 5 |
| 25 | Release Timing | 8,609 | 0.049 | 3.33e-05 | 3 |
| 26 | 30M Rel Vol | 8,609 | 0.048 | 4.44e-08 | 5 |
| 27 | 5M Rel Vol | 8,526 | 0.047 | 2.33e-07 | 5 |
| 28 | Fiscal Period | 8,609 | 0.047 | 7.82e-09 | 6 |
| 29 | 1M Rel Vol | 8,036 | 0.043 | 4.89e-05 | 5 |
| 30 | Sector | 7,857 | 0.040 | 0.0058 | 9 |
| 31 | Dollar Volume | 8,609 | 0.035 | 0.0047 | 6 |
| 32 | SPY | 8,609 | 0.030 | 0.1887 | 4 |

At 6M, the raw top of the table is dominated by **candle color**, especially end-of-day color. That does **not** mean you can use end-of-day color for a 9:35 AM entry. Among features known before or at the open, **ADR is still the clear leader**. Among early actionable confirmations, **10M Green** is unusually strong and remains strong after adjustment.

---

## 5. Core pre-entry/setup factors — full 6M bucket proof

### 5.1 ADR
Strong, monotonic-ish, replicates V3 and pre-2020. Best foundational universe/priority variable.

| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| 2-3% | 2,911 | 829 / 28.5% | 791 / 27.2% | 247 / 8.5% | 25 / 0.9% | 18.0% | 0.41 | 0.14 |
| 02 \| 3-4% | 2,278 | 522 / 22.9% | 852 / 37.4% | 382 / 16.8% | 80 / 3.5% | 23.0% | 0.80 | 0.59 |
| 03 \| 4-5% | 1,387 | 252 / 18.2% | 726 / 52.3% | 414 / 29.8% | 98 / 7.1% | 31.8% | 1.43 | 1.18 |
| 04 \| 5-7% | 1,259 | 227 / 18.0% | 677 / 53.8% | 435 / 34.6% | 176 / 14.0% | 32.8% | 1.66 | 2.33 |
| 05 \| 7-10% | 526 | 88 / 16.7% | 292 / 55.5% | 213 / 40.5% | 93 / 17.7% | 35.9% | 1.94 | 2.95 |
| 06 \| 10%+ | 248 | 52 / 21.0% | 154 / 62.1% | 104 / 41.9% | 44 / 17.7% | 41.6% | 2.01 | 2.96 |

### 5.2 Dollar Turnover
Strong raw separation. Relative activity to market cap is more informative than absolute liquidity.

| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <0.5% | 851 | 235 / 27.6% | 278 / 32.7% | 128 / 15.0% | 26 / 3.1% | 19.2% | 0.72 | 0.51 |
| 02 \| 0.5-1% | 2,852 | 692 / 24.3% | 1,002 / 35.1% | 440 / 15.4% | 93 / 3.3% | 21.2% | 0.74 | 0.54 |
| 03 \| 1-2% | 3,221 | 734 / 22.8% | 1,347 / 41.8% | 699 / 21.7% | 181 / 5.6% | 24.1% | 1.04 | 0.94 |
| 04 \| 2-5% | 1,451 | 272 / 18.7% | 724 / 49.9% | 424 / 29.2% | 165 / 11.4% | 29.7% | 1.40 | 1.90 |
| 05 \| 5-10% | 182 | 27 / 14.8% | 108 / 59.3% | 82 / 45.1% | 42 / 23.1% | 44.4% | 2.16 | 3.85 |
| 06 \| 10%+ | 52 | 10 / 19.2% | 33 / 63.5% | 22 / 42.3% | 9 / 17.3% | 40.4% | 2.03 | 2.89 |

### 5.3 Market Cap
Small caps are much more explosive raw, but market cap loses much of its independent effect once ADR/turnover/IPO/era are controlled.

| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <$1B | 600 | 105 / 17.5% | 352 / 58.7% | 225 / 37.5% | 93 / 15.5% | 37.4% | 1.80 | 2.59 |
| 02 \| $1-2B | 1,574 | 349 / 22.2% | 698 / 44.3% | 387 / 24.6% | 123 / 7.8% | 25.4% | 1.18 | 1.30 |
| 03 \| $2-5B | 2,688 | 616 / 22.9% | 1,091 / 40.6% | 552 / 20.5% | 132 / 4.9% | 23.5% | 0.98 | 0.82 |
| 04 \| $5-10B | 1,511 | 352 / 23.3% | 570 / 37.7% | 250 / 16.5% | 66 / 4.4% | 21.9% | 0.79 | 0.73 |
| 05 \| $10-25B | 1,192 | 290 / 24.3% | 441 / 37.0% | 224 / 18.8% | 60 / 5.0% | 21.9% | 0.90 | 0.84 |
| 06 \| $25-100B | 788 | 176 / 22.3% | 263 / 33.4% | 126 / 16.0% | 32 / 4.1% | 20.8% | 0.77 | 0.68 |
| 07 \| $100B+ | 256 | 82 / 32.0% | 77 / 30.1% | 31 / 12.1% | 10 / 3.9% | 18.8% | 0.58 | 0.65 |

### 5.4 ATH
The deep tail matters; the relationship is nonlinear. ≥70% and especially ≥85% below ATH enrich strongly, while a single continuous linear term does not capture it well.

| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| At ATH | 1,310 | 276 / 21.1% | 515 / 39.3% | 259 / 19.8% | 83 / 6.3% | 23.5% | 0.95 | 1.06 |
| 02 \| 0-10% below | 1,411 | 351 / 24.9% | 490 / 34.7% | 229 / 16.2% | 53 / 3.8% | 21.0% | 0.78 | 0.63 |
| 03 \| 10-25% below | 1,931 | 534 / 27.7% | 670 / 34.7% | 326 / 16.9% | 83 / 4.3% | 19.7% | 0.81 | 0.72 |
| 04 \| 25-50% below | 2,339 | 541 / 23.1% | 957 / 40.9% | 476 / 20.4% | 135 / 5.8% | 23.5% | 0.98 | 0.96 |
| 05 \| 50-70% below | 1,018 | 174 / 17.1% | 509 / 50.0% | 275 / 27.0% | 73 / 7.2% | 30.0% | 1.30 | 1.20 |
| 06 \| 70-85% below | 431 | 68 / 15.8% | 242 / 56.1% | 149 / 34.6% | 51 / 11.8% | 33.0% | 1.66 | 1.97 |
| 07 \| 85%+ below | 169 | 26 / 15.4% | 109 / 64.5% | 81 / 47.9% | 38 / 22.5% | 46.6% | 2.30 | 3.75 |

### 5.5 Gap
Large gaps show durable enrichment; ≥20% is a robust pre-specified threshold and stays significant in adjusted models.

| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| 5-7.5% | 3,543 | 856 / 24.2% | 1,320 / 37.3% | 615 / 17.4% | 138 / 3.9% | 21.7% | 0.83 | 0.65 |
| 02 \| 7.5-10% | 1,995 | 432 / 21.7% | 774 / 38.8% | 375 / 18.8% | 103 / 5.2% | 22.8% | 0.90 | 0.86 |
| 03 \| 10-15% | 1,820 | 411 / 22.6% | 784 / 43.1% | 431 / 23.7% | 137 / 7.5% | 25.0% | 1.14 | 1.26 |
| 04 \| 15-20% | 727 | 168 / 23.1% | 329 / 45.3% | 186 / 25.6% | 49 / 6.7% | 26.9% | 1.23 | 1.12 |
| 05 \| 20-30% | 427 | 83 / 19.4% | 227 / 53.2% | 145 / 34.0% | 68 / 15.9% | 33.0% | 1.63 | 2.66 |
| 06 \| 30%+ | 97 | 20 / 20.6% | 58 / 59.8% | 43 / 44.3% | 21 / 21.6% | 44.1% | 2.13 | 3.61 |

### 5.6 IPO Age
Younger names are more explosive, but 135 events have invalid IPO dates and are excluded. Treat this factor carefully.

| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <1 year | 343 | 77 / 22.4% | 158 / 46.1% | 104 / 30.3% | 34 / 9.9% | 25.6% | 1.45 | 1.65 |
| 02 \| 1-3 years | 896 | 191 / 21.3% | 441 / 49.2% | 258 / 28.8% | 82 / 9.2% | 29.3% | 1.38 | 1.53 |
| 03 \| 3-5 years | 955 | 218 / 22.8% | 419 / 43.9% | 239 / 25.0% | 87 / 9.1% | 25.7% | 1.20 | 1.52 |
| 04 \| 5-10 years | 1,425 | 305 / 21.4% | 623 / 43.7% | 322 / 22.6% | 102 / 7.2% | 25.6% | 1.08 | 1.19 |
| 05 \| 10-20 years | 1,620 | 378 / 23.3% | 623 / 38.5% | 295 / 18.2% | 65 / 4.0% | 22.9% | 0.87 | 0.67 |
| 06 \| 20+ years | 3,235 | 771 / 23.8% | 1,175 / 36.3% | 554 / 17.1% | 139 / 4.3% | 21.7% | 0.82 | 0.72 |

### 5.7 Dollar Volume
Weak/non-monotonic. Use primarily for liquidity/eligibility; turnover does more analytical work.

| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| $10-25M | 2,726 | 620 / 22.7% | 1,178 / 43.2% | 627 / 23.0% | 181 / 6.6% | 24.9% | 1.10 | 1.11 |
| 02 \| $25-50M | 1,793 | 412 / 23.0% | 755 / 42.1% | 392 / 21.9% | 118 / 6.6% | 24.3% | 1.05 | 1.10 |
| 03 \| $50-100M | 1,526 | 341 / 22.3% | 599 / 39.3% | 290 / 19.0% | 68 / 4.5% | 22.7% | 0.91 | 0.74 |
| 04 \| $100-250M | 1,393 | 331 / 23.8% | 527 / 37.8% | 259 / 18.6% | 73 / 5.2% | 22.5% | 0.89 | 0.87 |
| 05 \| $250M-1B | 930 | 209 / 22.5% | 335 / 36.0% | 173 / 18.6% | 52 / 5.6% | 21.8% | 0.89 | 0.93 |
| 06 \| $1B+ | 241 | 57 / 23.7% | 98 / 40.7% | 54 / 22.4% | 24 / 10.0% | 24.1% | 1.07 | 1.66 |

### 5.8 Prespecified 6M threshold summary
| Threshold | N | Sample share | 50%+ count/rate | 95% CI | 50% lift | 100%+ count/rate | 95% CI | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ADR >=5% | 2,033 | 23.6% | 752 / 37.0% | 34.9–39.1% | 1.77x | 313 / 15.4% | 13.9–17.0% | 2.57x |
| Turnover >=2% | 1,685 | 19.6% | 528 / 31.3% | 29.2–33.6% | 1.50x | 216 / 12.8% | 11.3–14.5% | 2.14x |
| Market Cap <$2B | 2,174 | 25.3% | 612 / 28.2% | 26.3–30.1% | 1.35x | 216 / 9.9% | 8.7–11.3% | 1.66x |
| ATH >=70% below | 600 | 7.0% | 230 / 38.3% | 34.5–42.3% | 1.84x | 89 / 14.8% | 12.2–17.9% | 2.47x |
| ATH >=85% below | 169 | 2.0% | 81 / 47.9% | 40.5–55.4% | 2.30x | 38 / 22.5% | 16.8–29.4% | 3.75x |
| Gap >=20% | 524 | 6.1% | 188 / 35.9% | 31.9–40.1% | 1.72x | 89 / 17.0% | 14.0–20.4% | 2.83x |

These thresholds were not chosen by searching V4 for the best cut. They are carry-forward V3 heuristics, which makes the older 2011–2019 portion a useful historical validation sample.

---

## 6. Historical validation: do the V3 heuristics work before 2020?

The most useful robustness test in V4 is not another p-value. It is asking whether thresholds learned in the recent V3 era still enrich outcomes in **pre-2020** data that was not available when the V3 findings were formed.
**Pre-2020 baseline:** N=2,525; +50% = 344 / 13.62%; +100% = 64 / 2.53%.
| Threshold | Flag N | 50%+ | Lift vs pre-2020 | 100%+ | Lift vs pre-2020 |
| :--- | ---: | ---: | ---: | ---: | ---: |
| ADR >=5% | 311 | 95 / 30.55% | 2.24x | 20 / 6.43% | 2.54x |
| Turnover >=2% | 546 | 98 / 17.95% | 1.32x | 21 / 3.85% | 1.52x |
| Market Cap <$2B | 693 | 115 / 16.59% | 1.22x | 18 / 2.60% | 1.02x |
| ATH >=70% below | 87 | 31 / 35.63% | 2.62x | 11 / 12.64% | 4.99x |
| ATH >=85% below | 15 | 7 / 46.67% | 3.43x | 3 / 20.00% | 7.89x |
| Gap >=20% | 95 | 30 / 31.58% | 2.32x | 11 / 11.58% | 4.57x |
| Revenue Surprise >=15% | 183 | 37 / 20.22% | 1.50x | 9 / 4.92% | 1.98x |
| EPS Surprise >=150% | 180 | 25 / 13.89% | 1.04x | 9 / 5.00% | 1.97x |
| Both Big Beats | 112 | 21 / 18.75% | 1.40x | 7 / 6.25% | 2.48x |
| Both Miss | 75 | 9 / 12.00% | 0.90x | 1 / 1.33% | 0.53x |
| Whole Day RVOL >=8x | 188 | 40 / 21.28% | 1.56x | 12 / 6.38% | 2.52x |
| 60M RVOL >=2.5x | 301 | 67 / 22.26% | 1.63x | 17 / 5.65% | 2.23x |
| 10M Green | 1,244 | 209 / 16.80% | 1.24x | 41 / 3.30% | 1.30x |
| 60M Green | 1,226 | 220 / 17.94% | 1.32x | 44 / 3.59% | 1.42x |
| Gap Day Green | 1,265 | 231 / 18.26% | 1.34x | 49 / 3.87% | 1.53x |

**What genuinely validates pre-2020:** ADR ≥5%, deep ATH drawdown, large gaps, extreme/persistent volume, and green price acceptance all improve outcomes. **What does not cleanly validate:** small market cap barely improves the +100% tail, and **Both Miss is actually worse than the pre-2020 baseline** (12.0% +50%, 1.3% +100%).

### 6.1 Period-by-period threshold stability
| Threshold | Pre-2020 50%/100% | 2020 50%/100% | 2021+ 50%/100% | 2023+ 50%/100% |
| :--- | ---: | ---: | ---: | ---: |
| ADR >=5% | 30.5% / 6.4% (N=311) | 64.6% / 30.4% (N=280) | 33.0% / 14.4% (N=1442) | 41.7% / 20.8% (N=817) |
| Turnover >=2% | 17.9% / 3.8% (N=546) | 60.3% / 30.1% (N=156) | 34.2% / 15.1% (N=983) | 38.3% / 18.4% (N=738) |
| Market Cap <$2B | 16.6% / 2.6% (N=693) | 55.8% / 23.9% (N=251) | 29.0% / 11.2% (N=1230) | 31.9% / 13.1% (N=949) |
| ATH >=70% below | 35.6% / 12.6% (N=87) | 86.4% / 47.7% (N=44) | 34.3% / 12.2% (N=469) | 38.5% / 15.8% (N=278) |
| Gap >=20% | 31.6% / 11.6% (N=95) | 53.2% / 38.3% (N=47) | 34.8% / 15.7% (N=382) | 37.5% / 18.1% (N=309) |
| Revenue Surprise >=15% | 20.2% / 4.9% (N=183) | 56.2% / 23.1% (N=121) | 29.9% / 10.4% (N=518) | 37.7% / 14.0% (N=308) |
| Both Big Beats | 18.8% / 6.2% (N=112) | 49.4% / 18.5% (N=81) | 33.1% / 11.0% (N=335) | 43.5% / 14.5% (N=193) |
| Both Miss | 12.0% / 1.3% (N=75) | 46.3% / 9.8% (N=41) | 29.6% / 13.8% (N=189) | 32.6% / 16.7% (N=138) |
| 60M RVOL >=2.5x | 22.3% / 5.6% (N=301) | 52.5% / 25.4% (N=59) | 31.6% / 14.0% (N=335) | 36.0% / 19.1% (N=225) |

The 2020 column is intentionally shown separately: almost every momentum/EP phenotype looks extraordinary there. A robust heuristic should not require 2020 to work. ADR, large gap, deep drawdown, extreme volume, and large revenue surprise pass that test better than the “Both Miss” anomaly.

---

## 7. Intraday volume: intensity, persistence, and redundancy

### 7.1 Whole-day relative volume
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <2x | 1,626 | 398 / 24.5% | 702 / 43.2% | 371 / 22.8% | 119 / 7.3% | 24.7% | 1.09 | 1.22 |
| 02 \| 2-3x | 2,316 | 617 / 26.6% | 829 / 35.8% | 400 / 17.3% | 91 / 3.9% | 21.0% | 0.83 | 0.66 |
| 03 \| 3-5x | 2,909 | 674 / 23.2% | 1,137 / 39.1% | 572 / 19.7% | 146 / 5.0% | 22.7% | 0.94 | 0.84 |
| 04 \| 5-8x | 1,284 | 209 / 16.3% | 571 / 44.5% | 303 / 23.6% | 102 / 7.9% | 26.5% | 1.13 | 1.33 |
| 05 \| 8x+ | 474 | 72 / 15.2% | 253 / 53.4% | 149 / 31.4% | 58 / 12.2% | 32.1% | 1.51 | 2.04 |

Whole-day RVOL is **U-shaped**, not cleanly monotonic: <2x is not weak, 2–5x is mediocre, and 8x+ is clearly strong. This is one reason whole-day RVOL should not be converted into a simplistic “higher is always better” score.

### 7.2 1M Rel Vol
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <0.01x ADV | 1,457 | 332 / 22.8% | 564 / 38.7% | 270 / 18.5% | 71 / 4.9% | 22.9% | 0.89 | 0.81 |
| 02 \| 0.01-0.03x ADV | 1,542 | 375 / 24.3% | 632 / 41.0% | 307 / 19.9% | 77 / 5.0% | 23.5% | 0.95 | 0.83 |
| 03 \| 0.03-0.05x ADV | 1,216 | 273 / 22.5% | 465 / 38.2% | 252 / 20.7% | 72 / 5.9% | 22.6% | 0.99 | 0.99 |
| 04 \| 0.05-0.10x ADV | 1,970 | 469 / 23.8% | 784 / 39.8% | 416 / 21.1% | 124 / 6.3% | 23.3% | 1.01 | 1.05 |
| 05 \| 0.10x+ ADV | 1,851 | 377 / 20.4% | 836 / 45.2% | 476 / 25.7% | 157 / 8.5% | 26.4% | 1.23 | 1.42 |

### 7.3 5M Rel Vol
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <0.05x ADV | 1,210 | 298 / 24.6% | 490 / 40.5% | 223 / 18.4% | 60 / 5.0% | 23.3% | 0.88 | 0.83 |
| 02 \| 0.05-0.10x ADV | 1,530 | 360 / 23.5% | 585 / 38.2% | 289 / 18.9% | 72 / 4.7% | 22.9% | 0.91 | 0.79 |
| 03 \| 0.10-0.17x ADV | 1,805 | 443 / 24.5% | 676 / 37.5% | 337 / 18.7% | 79 / 4.4% | 21.7% | 0.90 | 0.73 |
| 04 \| 0.17-0.30x ADV | 2,003 | 463 / 23.1% | 805 / 40.2% | 421 / 21.0% | 132 / 6.6% | 23.5% | 1.01 | 1.10 |
| 05 \| 0.30x+ ADV | 1,978 | 391 / 19.8% | 900 / 45.5% | 515 / 26.0% | 170 / 8.6% | 26.6% | 1.25 | 1.43 |

### 7.4 10M Rel Vol
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <0.10x ADV | 1,161 | 288 / 24.8% | 470 / 40.5% | 214 / 18.4% | 50 / 4.3% | 23.8% | 0.88 | 0.72 |
| 02 \| 0.10-0.18x ADV | 1,570 | 392 / 25.0% | 572 / 36.4% | 282 / 18.0% | 82 / 5.2% | 21.1% | 0.86 | 0.87 |
| 03 \| 0.18-0.30x ADV | 1,963 | 474 / 24.1% | 781 / 39.8% | 388 / 19.8% | 89 / 4.5% | 23.1% | 0.95 | 0.76 |
| 04 \| 0.30-0.45x ADV | 1,597 | 373 / 23.4% | 601 / 37.6% | 308 / 19.3% | 97 / 6.1% | 22.7% | 0.92 | 1.01 |
| 05 \| 0.45x+ ADV | 2,310 | 441 / 19.1% | 1,063 / 46.0% | 602 / 26.1% | 198 / 8.6% | 26.8% | 1.25 | 1.43 |

### 7.5 15M Rel Vol
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <0.15x ADV | 1,316 | 320 / 24.3% | 540 / 41.0% | 247 / 18.8% | 71 / 5.4% | 23.8% | 0.90 | 0.90 |
| 02 \| 0.15-0.25x ADV | 1,491 | 391 / 26.2% | 538 / 36.1% | 276 / 18.5% | 60 / 4.0% | 20.9% | 0.89 | 0.67 |
| 03 \| 0.25-0.35x ADV | 1,339 | 329 / 24.6% | 527 / 39.4% | 267 / 19.9% | 62 / 4.6% | 22.6% | 0.96 | 0.77 |
| 04 \| 0.35-0.60x ADV | 2,199 | 489 / 22.2% | 858 / 39.0% | 430 / 19.6% | 132 / 6.0% | 23.3% | 0.94 | 1.00 |
| 05 \| 0.60x+ ADV | 2,263 | 440 / 19.4% | 1,029 / 45.5% | 575 / 25.4% | 191 / 8.4% | 26.6% | 1.22 | 1.41 |

### 7.6 30M Rel Vol
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <0.25x ADV | 1,230 | 303 / 24.6% | 507 / 41.2% | 244 / 19.8% | 71 / 5.8% | 23.7% | 0.95 | 0.96 |
| 02 \| 0.25-0.40x ADV | 1,481 | 388 / 26.2% | 540 / 36.5% | 266 / 18.0% | 65 / 4.4% | 21.4% | 0.86 | 0.73 |
| 03 \| 0.40-0.60x ADV | 1,680 | 415 / 24.7% | 638 / 38.0% | 316 / 18.8% | 74 / 4.4% | 22.3% | 0.90 | 0.73 |
| 04 \| 0.60-0.90x ADV | 1,740 | 405 / 23.3% | 682 / 39.2% | 353 / 20.3% | 108 / 6.2% | 23.0% | 0.97 | 1.04 |
| 05 \| 0.90x+ ADV | 2,478 | 459 / 18.5% | 1,125 / 45.4% | 616 / 24.9% | 198 / 8.0% | 26.6% | 1.19 | 1.33 |

### 7.7 60M Rel Vol
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <0.40x ADV | 1,149 | 289 / 25.2% | 478 / 41.6% | 232 / 20.2% | 70 / 6.1% | 23.6% | 0.97 | 1.02 |
| 02 \| 0.40-0.65x ADV | 1,630 | 426 / 26.1% | 599 / 36.7% | 294 / 18.0% | 70 / 4.3% | 21.6% | 0.87 | 0.72 |
| 03 \| 0.65-0.90x ADV | 1,462 | 369 / 25.2% | 542 / 37.1% | 266 / 18.2% | 65 / 4.4% | 22.7% | 0.87 | 0.74 |
| 04 \| 0.90-1.40x ADV | 1,996 | 449 / 22.5% | 794 / 39.8% | 409 / 20.5% | 117 / 5.9% | 22.8% | 0.98 | 0.98 |
| 05 \| 1.40x+ ADV | 2,372 | 437 / 18.4% | 1,079 / 45.5% | 594 / 25.0% | 194 / 8.2% | 26.7% | 1.20 | 1.36 |

### 7.8 Persistence correlations
| Pair | N | Spearman ρ | p-value |
| :--- | ---: | ---: | ---: |
| 1M vs 60M | 8,036 | 0.545 | 0.00e+00 |
| 5M vs 60M | 8,526 | 0.839 | 0.00e+00 |
| 10M vs 60M | 8,601 | 0.919 | 0.00e+00 |
| 30M vs 60M | 8,609 | 0.981 | 0.00e+00 |
| 60M vs Day | 8,609 | 0.902 | 0.00e+00 |

The message is redundancy: by 10 minutes, the cumulative RVOL measures are extremely correlated with the 60-minute measure (ρ=0.919), and 60M vs whole-day is ρ=0.902. **Do not put 5M, 10M, 15M, 30M, and 60M RVOL simultaneously into a final scoring model** and pretend they are five independent signals.

### 7.9 Conditional persistence after a strong first minute
Among events already trading at least 0.10x ADV in the first minute:
| 60M RVOL bucket | N | 50%+ | 100%+ | Median MFE |
| :--- | ---: | ---: | ---: | ---: |
| 01 \| <0.9x | 91 | 22 / 24.18% | 5 / 5.49% | 24.25% |
| 02 \| 0.9-1.4x | 402 | 88 / 21.89% | 24 / 5.97% | 22.90% |
| 03 \| 1.4-2.5x | 843 | 208 / 24.67% | 65 / 7.71% | 25.59% |
| 04 \| 2.5x+ | 515 | 158 / 30.68% | 63 / 12.23% | 30.41% |

Persistence adds information even after an intense first minute: the ≥2.5x first-hour group reaches +50% **30.68%** and +100% **12.23%**. V3’s persistence signal therefore replicates directionally, though the full-history effect is weaker than the recent-sample effect.

---

## 8. Green/red candle acceptance: the strongest actionable intraday finding

A green candle here means the cumulative candle close is above the gap-day open. This is not merely “volume”; it is **acceptance above the open after the market has had time to trade the news**.

| Observation | Green N | Green 50%+ | Green 100%+ | Red N | Red 50%+ | Red 100%+ | 50% spread |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1M | 3,883 | 22.38% | 6.62% | 4,153 | 20.52% | 5.88% | +1.9 pp |
| 5M | 4,070 | 24.23% | 7.03% | 4,456 | 17.93% | 5.09% | +6.3 pp |
| 10M | 4,135 | 25.05% | 7.42% | 4,466 | 16.97% | 4.68% | +8.1 pp |
| 15M | 4,068 | 25.12% | 7.40% | 4,540 | 17.03% | 4.74% | +8.1 pp |
| 30M | 4,107 | 24.88% | 7.16% | 4,502 | 17.17% | 4.93% | +7.7 pp |
| 60M | 4,098 | 25.13% | 7.30% | 4,511 | 16.96% | 4.81% | +8.2 pp |
| Day | 4,173 | 26.05% | 7.60% | 4,436 | 15.96% | 4.49% | +10.1 pp |

The 1-minute color spread is small. By **5–10 minutes**, the separation becomes substantial and remains stable through the day. This timing matters: 10M Green is early enough to be a plausible entry filter, unlike gap-day color which is only known at the close.

### 8.1 Same comparison inside ADR ≥5%
| Observation | Green N | Green 50%+ | Green 100%+ | Red N | Red 50%+ | Red 100%+ | 50% spread |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1M | 939 | 40.58% | 16.29% | 1,042 | 34.36% | 14.88% | +6.2 pp |
| 5M | 940 | 42.98% | 17.34% | 1,087 | 31.92% | 13.71% | +11.1 pp |
| 10M | 934 | 43.58% | 17.77% | 1,098 | 31.42% | 13.39% | +12.2 pp |
| 15M | 904 | 44.47% | 17.81% | 1,128 | 31.03% | 13.48% | +13.4 pp |
| 30M | 915 | 43.39% | 17.49% | 1,118 | 31.75% | 13.69% | +11.6 pp |
| 60M | 911 | 44.79% | 17.78% | 1,122 | 30.66% | 13.46% | +14.1 pp |
| Day | 912 | 45.29% | 18.64% | 1,121 | 30.24% | 12.76% | +15.0 pp |

Inside the high-ADR universe, 10M Green produces **407 / 934 = 43.58%** +50% and **166 / 934 = 17.77%** +100%, versus 10M Red **345 / 1,098 = 31.42%** and **147 / 1,098 = 13.39%**. The “green” effect is therefore not just a low-ADR versus high-ADR confound.

### 8.2 Color × volume: participation only matters if price accepts it
Exact numeric 60M ≥2.5x split (all mature events):
| Condition | N | 50%+ | 100%+ | Median MFE |
| :--- | ---: | ---: | ---: | ---: |
| Green, 60M RVOL <2.5x | 3,611 | 24.0% | 6.4% | — |
| Red, 60M RVOL <2.5x | 4,303 | 16.9% | 4.8% | — |
| Green, 60M RVOL ≥2.5x | 487 | 33.9% | 14.2% | 35.0% |
| Red, 60M RVOL ≥2.5x | 208 | 18.8% | 4.8% | 20.5% |

Inside ADR ≥5%: **Green + ≥2.5x** = 59 / 118 +50% (**50.0%**) and 29 / 118 +100% (**24.6%**); **Red + ≥2.5x** = 19 / 56 (**33.9%**) and 7 / 56 (**12.5%**). High volume on a red first-hour candle does not create the same edge as high volume with acceptance.

At 10M inside ADR ≥5%, **Green + ≥0.45x ADV** = N=301, +50% 145 / 301 = **48.17%**, +100% 69 / 301 = **22.92%**. The corresponding Red + ≥0.45x group is 34.7% / 16.0%.

---

## 9. Catalyst and fundamental features

### 9.1 Revenue Surprise
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Miss (<0%) | 1,245 | 282 / 22.7% | 498 / 40.0% | 263 / 21.1% | 77 / 6.2% | 23.3% | 1.01 | 1.03 |
| 02 \| 0-0.5% | 430 | 109 / 25.3% | 168 / 39.1% | 64 / 14.9% | 10 / 2.3% | 21.7% | 0.71 | 0.39 |
| 03 \| 0.5-2.25% | 1,660 | 412 / 24.8% | 551 / 33.2% | 236 / 14.2% | 67 / 4.0% | 21.0% | 0.68 | 0.67 |
| 04 \| 2.25-4.5% | 1,639 | 431 / 26.3% | 612 / 37.3% | 289 / 17.6% | 75 / 4.6% | 21.5% | 0.85 | 0.76 |
| 05 \| 4.5-8.5% | 1,487 | 319 / 21.5% | 624 / 42.0% | 343 / 23.1% | 87 / 5.9% | 24.4% | 1.11 | 0.98 |
| 06 \| 8.5-15% | 907 | 180 / 19.8% | 415 / 45.8% | 234 / 25.8% | 69 / 7.6% | 27.2% | 1.24 | 1.27 |
| 07 \| 15%+ | 822 | 145 / 17.6% | 432 / 52.6% | 260 / 31.6% | 91 / 11.1% | 32.6% | 1.52 | 1.85 |

### 9.2 EPS Surprise
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Miss (<0%) | 952 | 224 / 23.5% | 425 / 44.6% | 245 / 25.7% | 72 / 7.6% | 26.1% | 1.23 | 1.26 |
| 02 \| 0-5% | 844 | 212 / 25.1% | 270 / 32.0% | 118 / 14.0% | 33 / 3.9% | 20.3% | 0.67 | 0.65 |
| 03 \| 5-15% | 1,590 | 430 / 27.0% | 513 / 32.3% | 217 / 13.6% | 51 / 3.2% | 19.8% | 0.65 | 0.53 |
| 04 \| 15-30% | 1,566 | 356 / 22.7% | 619 / 39.5% | 288 / 18.4% | 71 / 4.5% | 23.0% | 0.88 | 0.76 |
| 05 \| 30-70% | 1,605 | 336 / 20.9% | 687 / 42.8% | 376 / 23.4% | 106 / 6.6% | 25.0% | 1.12 | 1.10 |
| 06 \| 70-150% | 848 | 169 / 19.9% | 398 / 46.9% | 229 / 27.0% | 71 / 8.4% | 27.1% | 1.30 | 1.40 |
| 07 \| 150%+ | 775 | 151 / 19.5% | 385 / 49.7% | 218 / 28.1% | 81 / 10.5% | 29.5% | 1.35 | 1.74 |

### 9.3 Surprise Matrix
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Both Big Beats | 528 | 86 / 16.3% | 289 / 54.7% | 172 / 32.6% | 59 / 11.2% | 34.0% | 1.56 | 1.86 |
| 02 \| Big EPS + Revenue Beat | 2,382 | 513 / 21.5% | 1,037 / 43.5% | 567 / 23.8% | 171 / 7.2% | 25.3% | 1.14 | 1.20 |
| 03 \| Big EPS Beat + Revenue Miss | 292 | 53 / 18.2% | 133 / 45.5% | 77 / 26.4% | 26 / 8.9% | 26.7% | 1.26 | 1.49 |
| 04 \| EPS Beat + Big Revenue Beat | 167 | 31 / 18.6% | 81 / 48.5% | 50 / 29.9% | 18 / 10.8% | 27.6% | 1.44 | 1.80 |
| 05 \| Both Positive, Neither Big | 3,154 | 797 / 25.3% | 1,076 / 34.1% | 467 / 14.8% | 112 / 3.6% | 20.9% | 0.71 | 0.59 |
| 06 \| EPS Beat + Revenue Miss | 617 | 154 / 25.0% | 219 / 35.5% | 95 / 15.4% | 19 / 3.1% | 20.8% | 0.74 | 0.51 |
| 07 \| EPS Miss + Big Revenue Beat | 100 | 23 / 23.0% | 50 / 50.0% | 30 / 30.0% | 12 / 12.0% | 29.9% | 1.44 | 2.00 |
| 08 \| EPS Miss + Revenue Beat | 501 | 120 / 24.0% | 220 / 43.9% | 115 / 23.0% | 24 / 4.8% | 24.8% | 1.10 | 0.80 |
| 09 \| Both Miss | 305 | 69 / 22.6% | 131 / 43.0% | 84 / 27.5% | 31 / 10.2% | 25.7% | 1.32 | 1.70 |

### 9.4 EPS YoY
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Profit -> Loss | 220 | 28 / 12.7% | 126 / 57.3% | 89 / 40.5% | 33 / 15.0% | 39.7% | 1.94 | 2.50 |
| 02 \| Loss Worsening | 384 | 82 / 21.4% | 189 / 49.2% | 127 / 33.1% | 54 / 14.1% | 29.3% | 1.59 | 2.35 |
| 03 \| Loss Narrowing | 780 | 148 / 19.0% | 425 / 54.5% | 271 / 34.7% | 117 / 15.0% | 33.2% | 1.67 | 2.50 |
| 04 \| Loss -> Profit | 714 | 171 / 23.9% | 319 / 44.7% | 202 / 28.3% | 70 / 9.8% | 25.8% | 1.36 | 1.64 |
| 05 \| Positive EPS Decline | 1,577 | 355 / 22.5% | 643 / 40.8% | 292 / 18.5% | 51 / 3.2% | 24.1% | 0.89 | 0.54 |
| 06 \| EPS Growth 0-25% | 1,641 | 386 / 23.5% | 539 / 32.8% | 206 / 12.6% | 45 / 2.7% | 20.2% | 0.60 | 0.46 |
| 07 \| EPS Growth 25-50% | 1,108 | 263 / 23.7% | 393 / 35.5% | 163 / 14.7% | 19 / 1.7% | 21.3% | 0.71 | 0.29 |
| 08 \| EPS Growth 50-100% | 747 | 202 / 27.0% | 258 / 34.5% | 110 / 14.7% | 29 / 3.9% | 20.7% | 0.71 | 0.65 |
| 09 \| EPS Growth 100%+ | 945 | 214 / 22.6% | 395 / 41.8% | 218 / 23.1% | 60 / 6.3% | 23.9% | 1.11 | 1.06 |

### 9.5 Rev YoY
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Negative | 1,753 | 363 / 20.7% | 782 / 44.6% | 419 / 23.9% | 114 / 6.5% | 26.5% | 1.15 | 1.08 |
| 02 \| 0-10% | 1,810 | 420 / 23.2% | 638 / 35.2% | 275 / 15.2% | 61 / 3.4% | 21.3% | 0.73 | 0.56 |
| 03 \| 10-20% | 1,449 | 380 / 26.2% | 519 / 35.8% | 248 / 17.1% | 72 / 5.0% | 20.8% | 0.82 | 0.83 |
| 04 \| 20-35% | 1,292 | 293 / 22.7% | 523 / 40.5% | 256 / 19.8% | 63 / 4.9% | 23.0% | 0.95 | 0.81 |
| 05 \| 35-100% | 1,304 | 292 / 22.4% | 584 / 44.8% | 323 / 24.8% | 109 / 8.4% | 26.3% | 1.19 | 1.39 |
| 06 \| 100%+ | 477 | 94 / 19.7% | 225 / 47.2% | 150 / 31.4% | 54 / 11.3% | 28.2% | 1.51 | 1.89 |

### 9.6 Key catalyst thresholds
| Threshold | N | Sample share | 50%+ count/rate | 95% CI | 50% lift | 100%+ count/rate | 95% CI | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Revenue Surprise >=15% | 822 | 10.0% | 260 / 31.6% | 28.5–34.9% | 1.53x | 91 / 11.1% | 9.1–13.4% | 1.90x |
| EPS Surprise >=150% | 775 | 9.5% | 218 / 28.1% | 25.1–31.4% | 1.36x | 81 / 10.5% | 8.5–12.8% | 1.76x |
| Both Big Beats | 528 | 6.6% | 172 / 32.6% | 28.7–36.7% | 1.58x | 59 / 11.2% | 8.8–14.1% | 1.90x |
| Both Miss | 305 | 3.8% | 84 / 27.5% | 22.8–32.8% | 1.34x | 31 / 10.2% | 7.3–14.1% | 1.73x |

**Both Miss requires a reversal of the V3 interpretation.** In the recent sample it looked like a potential “expectations reset” phenomenon, but V4 shows it is not historically stable. Pre-2020 Both Miss is below baseline; in adjusted full-history models it has OR ≈1.05 for +50% (p=.735) and OR ≈1.10 for +100% (p=.655). Do not build a timeless filter around it.

### 9.7 Incremental catalyst models after technical + era controls
| Feature | OR 50%+ | 95% CI | p | OR 100%+ | 95% CI | p |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| RevSurp>=15 | 1.51 | 1.26–1.82 | 1.34e-05 | 1.47 | 1.12–1.92 | 0.0051 |
| EPSsurp>=150 | 1.30 | 1.09–1.55 | 0.0041 | 1.52 | 1.15–2.00 | 0.0031 |
| BothBigBeats | 1.60 | 1.29–2.00 | 2.57e-05 | 1.42 | 1.03–1.95 | 0.0302 |
| BothMiss | 1.05 | 0.79–1.39 | 0.7349 | 1.10 | 0.72–1.70 | 0.6551 |
| EPSlossTransition | 1.80 | 1.57–2.08 | 1.68e-16 | 2.59 | 2.01–3.35 | 2.87e-13 |
| RevYoY>=35 | 1.59 | 1.37–1.84 | 5.19e-10 | 1.82 | 1.42–2.33 | 2.12e-06 |
| RevYoY>=100 | 1.49 | 1.19–1.87 | 0.0005 | 1.45 | 1.05–2.00 | 0.0259 |
| AfterClose | 1.23 | 1.08–1.40 | 0.0021 | 1.43 | 1.15–1.78 | 0.0015 |
| 4W<-20 | 1.02 | 0.80–1.30 | 0.8529 | 0.91 | 0.65–1.27 | 0.5810 |
| 4W>20 | 1.19 | 0.96–1.47 | 0.1049 | 1.11 | 0.82–1.52 | 0.4936 |

The strongest catalyst-style result here is **EPS loss/transition state** (OR 1.80 for +50%, 2.59 for +100%) followed by strong revenue growth. Because EPS state can be sensitive to accounting basis and near-zero denominators, it deserves direct source-quality validation before becoming a hard rule.

---

## 10. Multivariable robustness: what survives when factors compete?

The following models use **cluster-robust standard errors by ticker** and include reaction-era controls. They are not strategy backtests. Odds ratios above 1 indicate higher conditional odds of the outcome.

### 10.1 10-minute actionable model
**+50% outcome:**
| Feature | Odds ratio | 95% CI | p-value |
| :--- | ---: | ---: | ---: |
| ADR>=5% | 2.69 | 2.34–3.09 | 7.23e-44 |
| Turnover>=2% | 1.35 | 1.18–1.55 | 2.25e-05 |
| MC<$2B | 1.19 | 1.03–1.37 | 0.0149 |
| ATH>=70% below | 1.51 | 1.21–1.87 | 0.0002 |
| Gap>=20% | 1.29 | 1.04–1.59 | 0.0192 |
| 10M Green | 1.66 | 1.48–1.87 | 3.37e-18 |
| 10M RVOL>=0.45x | 1.52 | 1.33–1.74 | 8.70e-10 |

**+100% outcome:**
| Feature | Odds ratio | 95% CI | p-value |
| :--- | ---: | ---: | ---: |
| ADR>=5% | 4.28 | 3.41–5.37 | 2.78e-36 |
| Turnover>=2% | 1.73 | 1.38–2.17 | 2.51e-06 |
| MC<$2B | 1.19 | 0.94–1.50 | 0.1419 |
| ATH>=70% below | 1.35 | 0.99–1.82 | 0.0553 |
| Gap>=20% | 1.74 | 1.28–2.36 | 0.0004 |
| 10M Green | 1.63 | 1.34–2.00 | 1.78e-06 |
| 10M RVOL>=0.45x | 1.69 | 1.36–2.11 | 2.82e-06 |

Interpretation: **ADR is by far the strongest independent technical feature**, especially for the +100% tail. Turnover, big gap, 10M Green, and 10M RVOL all add information. Market cap remains significant for +50% but is **not significant for +100%** after the other variables are included. ATH ≥70% is strong for +50% and borderline for +100%.

### 10.2 60-minute confirmation model
**+50% outcome:**
| Feature | Odds ratio | 95% CI | p-value |
| :--- | ---: | ---: | ---: |
| ADR>=5% | 2.66 | 2.31–3.06 | 2.15e-42 |
| Turnover>=2% | 1.38 | 1.20–1.59 | 6.05e-06 |
| MC<$2B | 1.19 | 1.03–1.37 | 0.0158 |
| ATH>=70% below | 1.49 | 1.20–1.85 | 0.0003 |
| Gap>=20% | 1.41 | 1.14–1.75 | 0.0013 |
| 60M Green | 1.77 | 1.58–1.99 | 3.14e-23 |
| 60M RVOL>=2.5x | 1.41 | 1.15–1.73 | 0.0011 |

**+100% outcome:**
| Feature | Odds ratio | 95% CI | p-value |
| :--- | ---: | ---: | ---: |
| ADR>=5% | 4.24 | 3.39–5.31 | 3.02e-36 |
| Turnover>=2% | 1.76 | 1.40–2.21 | 1.04e-06 |
| MC<$2B | 1.18 | 0.94–1.49 | 0.1605 |
| ATH>=70% below | 1.34 | 0.99–1.81 | 0.0591 |
| Gap>=20% | 1.84 | 1.35–2.52 | 0.0001 |
| 60M Green | 1.66 | 1.37–2.01 | 2.76e-07 |
| 60M RVOL>=2.5x | 1.76 | 1.28–2.41 | 0.0005 |

The 60M model tells the same story. Volume persistence and green acceptance both add information, but you do not need both 10M and 60M models in one production score. Choose an **entry timing** first, then use the information available at that time.

### 10.3 Continuous-model sanity check
A separate continuous specification produces the same hierarchy: standardized log(ADR) OR ≈1.83 for +50% and ≈2.04 for +100%; turnover and gap remain useful; continuous market cap and continuous ATH distance become weak once correlated variables are present; 10M/60M Green and RVOL remain significant. This is consistent with **nonlinear threshold effects** for deep ATH drawdown and with market cap partly proxying for ADR/turnover.

---

## 11. Redundancy and confounding

| Pair | N | Spearman ρ | p-value |
| :--- | ---: | ---: | ---: |
| ADR vs Log Market Cap | 8,609 | -0.283 | 6.20e-158 |
| ADR vs Turnover % | 8,609 | 0.347 | 3.79e-242 |
| Turnover % vs Log Market Cap | 8,609 | -0.305 | 1.75e-184 |
| Gap % vs ADR | 8,609 | 0.226 | 1.62e-100 |
| Gap % vs Turnover % | 8,609 | 0.168 | 2.08e-55 |
| Below ATH % vs ADR | 8,609 | 0.449 | 0.00e+00 |
| 10M RVOL vs 60M RVOL | 8,601 | 0.919 | 0.00e+00 |
| 1M RVOL vs 10M RVOL | 8,036 | 0.636 | 0.00e+00 |
| 60M RVOL vs Day RVOL | 8,609 | 0.902 | 0.00e+00 |

Key implications:
- **ADR vs deep ATH drawdown:** ρ=0.449. Destroyed stocks are often high-ADR stocks, so the raw ATH effect is partly a volatility phenotype.
- **ADR vs turnover:** ρ=0.347. They overlap, but not enough to make turnover redundant; both survive adjusted models.
- **ADR vs market cap:** ρ=-0.283. Small stocks are more volatile, explaining why market cap weakens after ADR controls.
- **10M vs 60M RVOL:** ρ=0.919. Multiple cumulative volume horizons are nearly duplicate information. Pick one based on entry timing.

---

## 12. Repeated ticker robustness and monster concentration

A stock can produce multiple qualifying earnings gaps across years, so ordinary row-level inference can be overconfident if a few serial winners dominate. Two checks address this.

### 12.1 First mature EP per ticker only
First-event sample: **N=1,987**, baseline +50% = **20.6%**, +100% = **5.7%**.
| Threshold | Flag N | 50%+ | 100%+ |
| :--- | ---: | ---: | ---: |
| ADR >=5% | 588 | 35.9% | 13.4% |
| Turnover >=2% | 335 | 30.1% | 11.0% |
| Market Cap <$2B | 651 | 27.3% | 9.5% |
| ATH >=70% below | 122 | 34.4% | 10.7% |
| ATH >=85% below | 36 | 44.4% | 13.9% |
| Gap >=20% | 98 | 36.7% | 18.4% |
| Whole Day RVOL >=8x | 108 | 35.2% | 14.8% |
| 60M RVOL >=2.5x | 148 | 33.8% | 12.8% |
| 10M Green | 922 | 24.0% | 6.8% |
| 60M Green | 929 | 25.4% | 7.4% |
| Gap Day Green | 955 | 25.0% | 7.0% |

The core effects survive when each ticker contributes only once. This is especially reassuring for ADR, big gap, deep ATH drawdown, extreme volume, and green confirmation.

### 12.2 How concentrated are 6M doubles?
There are **516** 6M +100% events across **338 unique tickers**. The top 20 tickers account for only **15.5%** of all double events.
| Ticker | 6M double events |
| :--- | ---: |
| AAOI | 6 |
| UPST | 6 |
| TSLA | 5 |
| NVDA | 4 |
| SEDG | 4 |
| ANF | 4 |
| ROKU | 4 |
| TWLO | 4 |
| CVNA | 4 |
| NTRA | 4 |
| CELH | 4 |
| SITM | 4 |
| PLTR | 4 |
| VRT | 4 |
| APP | 4 |
| Z | 3 |
| GRPN | 3 |
| EXEL | 3 |
| AMD | 3 |
| MDB | 3 |

The outlier tail is therefore not an illusion created by two or three meme names, although clustered standard errors remain appropriate because repeat observations are not independent.

---

## 13. Secondary / exploratory variables

### 13.1 4-week price change

#### 4-week momentum
| Group | N | 50%+ | 100%+ | Median MFE |
| :--- | ---: | ---: | ---: | ---: |
| 01 \| <-20% | 433 | 33.03% | 12.01% | 30.54% |
| 02 \| -20 to -5% | 2,195 | 19.36% | 5.10% | 22.37% |
| 03 \| -5 to +5% | 3,075 | 17.30% | 4.07% | 21.90% |
| 04 \| +5 to +20% | 2,297 | 20.59% | 6.09% | 24.19% |
| 05 \| +20%+ | 609 | 36.45% | 14.29% | 34.01% |

#### Release timing
| Group | N | 50%+ | 100%+ | Median MFE |
| :--- | ---: | ---: | ---: | ---: |
| AFTER_CLOSE | 5,237 | 22.09% | 6.74% | 24.16% |
| BEFORE_OPEN | 3,367 | 18.89% | 4.84% | 22.69% |
| DURING_MARKET | 5 | 40.00% | 0.00% | 39.04% |

#### Fiscal period
| Group | N | 50%+ | 100%+ | Median MFE |
| :--- | ---: | ---: | ---: | ---: |
| FY | 4 | 25.00% | 0.00% | 10.04% |
| H1 | 4 | 25.00% | 0.00% | 16.87% |
| Q1 | 2,067 | 25.11% | 8.13% | 27.40% |
| Q2 | 2,136 | 19.48% | 5.71% | 22.78% |
| Q3 | 2,235 | 20.85% | 5.37% | 23.87% |
| Q4 | 2,163 | 18.12% | 4.90% | 20.70% |

4-week momentum is U-shaped raw (very negative and very positive moves both look strong) but neither extreme survives adjusted controls. Treat it as phenotype/context, not a core hard filter. After-close reports outperform before-open reports after controls (OR 1.23 for +50%, 1.43 for +100%), which is interesting but should be tested with execution assumptions because release timing changes how much price discovery occurs before the opening print.

### 13.2 Sector
| Sector | N | 50%+ | 100%+ | Median MFE |
| :--- | ---: | ---: | ---: | ---: |
| Agriculture, Forestry, Fishing | 5 | 0.00% | 0.00% | 6.04% |
| Construction | 189 | 29.63% | 8.99% | 31.56% |
| Finance, Insurance, Real Estate | 645 | 19.69% | 6.20% | 23.10% |
| Manufacturing | 3,476 | 21.58% | 6.50% | 24.40% |
| Mining | 191 | 28.27% | 10.47% | 27.87% |
| Retail Trade | 801 | 17.60% | 4.74% | 20.81% |
| Services | 2,070 | 19.13% | 5.27% | 22.92% |
| Transportation & Utilities | 352 | 18.18% | 4.26% | 22.69% |
| Wholesale Trade | 128 | 10.94% | 2.34% | 20.64% |

Sector association is weak overall (6M Cramér V ≈0.040). It is useful for descriptive breakdowns and perhaps controls, not as a primary selection rule from this dataset.

### 13.3 SPY Chillax regime
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Green | 4,776 | 1,119 / 23.4% | 1,878 / 39.3% | 952 / 19.9% | 279 / 5.8% | 22.9% | 0.96 | 0.97 |
| 02 \| Light Green | 311 | 64 / 20.6% | 140 / 45.0% | 84 / 27.0% | 22 / 7.1% | 26.8% | 1.30 | 1.18 |
| 03 \| Yellow | 134 | 33 / 24.6% | 52 / 38.8% | 32 / 23.9% | 10 / 7.5% | 23.8% | 1.15 | 1.25 |
| 04 \| Downtrend | 3,388 | 754 / 22.3% | 1,422 / 42.0% | 727 / 21.5% | 205 / 6.1% | 24.3% | 1.03 | 1.01 |

The raw SPY Chillax categories are much weaker than year/era. This does not mean market context is irrelevant; rather, this particular four-state proxy does not summarize the regime differences nearly as well as realized reaction-year/era does.

---

## 14. What I would carry into the execution backtest

This section is **not** a final trading system. It is a research triage: which features have enough evidence to deserve entry/exit backtesting, which should be secondary stratifiers, and which should be dropped or delayed.

| Tier | Feature | Why it survives this analysis | Observability |
| :--- | :--- | :--- | :--- |
| A — core | ADR | Strongest pre-entry factor; monotonic buckets; pre-2020 replication; largest adjusted OR. | Known before open |
| A — core | Reaction year/era | Massive regime differences; prevents pooled-average illusion. | Known before open |
| A — core | Gap % | Robust threshold; pre-2020 validation; remains adjusted predictor. | Known at open |
| A — core | Dollar turnover % | Strong raw enrichment; independent of ADR enough to survive models. | Known before open |
| A — entry confirmation | 10M Green | Early actionable price-acceptance signal; strong adjusted effect. | Known after 10 min |
| A — entry confirmation | 10M RVOL | Adds independent information beside color and ADR; correlated with later RVOL. | Known after 10 min |
| B — enrichment | ATH drawdown | Deep tails strongly enriched and historically validated; nonlinear; partially overlaps ADR. | Known before open |
| B — enrichment | IPO age | Younger names stronger; some independent effect; data QC issue on 135 events. | Known before open if date valid |
| B — enrichment | Market cap | Strong raw phenotype, weaker independent effect—especially for doubles. | Known before open |
| B — catalyst | Revenue surprise | Monotonic-ish; ≥15% validates and survives technical controls. | Known on report |
| B — catalyst | Both Big Beats | Replicates directionally; incremental value but overlaps other catalyst fields. | Known on report |
| B — catalyst | EPS loss/transition / Rev growth | Strong adjusted association, but accounting/data-definition caution. | Known on report |
| C — later confirmation | 60M Green + RVOL | Very useful if strategy intentionally waits an hour; redundant for a 10M entry model. | Known after 60 min |
| C — EOD | Gap-day color / whole-day RVOL | Strong descriptive signal, but unavailable for morning entry. | Known at/after close |
| Drop as core | Absolute 30D dollar volume | Weak/non-monotonic beyond minimum liquidity constraint. | Known before open |
| Drop as timeless | Both Miss | Fails pre-2020 and full-history adjusted validation. | Known on report |
| Low priority | SPY Chillax state | Weak raw association compared with year/era. | Known before open |
| Low priority | Sector / fiscal quarter / 4W momentum | Weak or explained by stronger correlated factors. | Known before open |

**Practical next-stage design principle:** do not optimize entry and exit simultaneously across dozens of features. Start with a small set of structurally validated selectors (ADR, gap, turnover, perhaps deep ATH/catalyst), then test a small number of entry timings (open/1M/5M/10M/15M/30M/60M) using only information available by that time, and finally test exit families. Otherwise the next stage will become parameter mining.

---

## 15. Manual verification guide — how to reproduce the numbers in Excel

This section is deliberately redundant so you can audit the report yourself instead of trusting the calculations.

### 15.1 Add helper columns (recommended copy of workbook)
```excel
Unique Event =COUNTIFS($A$2:A2,A2,$B$2:B2,B2)=1
Reaction Year =YEAR(A2)
6M Mature =A2<=DATE(2026,2,21)
3M Mature =A2<=DATE(2026,5,21)
1M Mature =A2<=DATE(2026,7,21)
6M 50%+ =DB2>=0.5
6M 100%+ =DB2>=1
```

To match the report exactly for technical/outcome statistics, filter **Unique Event=TRUE** and the relevant maturity helper. For fundamental statistics, exclude all rows belonging to the three duplicate event keys listed in §1.1.

### 15.2 Baseline proof
- Filter `reaction_date <= 2/21/2026` and Unique Event=TRUE.
- Expected 6M mature N = **8,609** (raw workbook without dedupe = **8,615**).
- Count `DB >= 0.50`: **1,795** → 1,795 / 8,609 = **20.850%**.
- Count `DB >= 1.00`: **516** → 516 / 8,609 = **5.994%**.

### 15.3 Key threshold proof table
| Condition | Workbook filter | N | 50% count | 50% rate | 100% count | 100% rate |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: |
| ADR ≥5% | AE >= 5 (or AF buckets 04–06) | 2,033 | 752 | 37.0% | 313 | 15.4% |
| Turnover ≥2% | DG >= 2 (or DH buckets 04–06) | 1,685 | 528 | 31.3% | 216 | 12.8% |
| Market cap <$2B | AG < 2000000000 (or AH 01–02) | 2,174 | 612 | 28.2% | 216 | 9.9% |
| ATH ≥70% below | AS buckets 06–07 | 600 | 230 | 38.3% | 89 | 14.8% |
| ATH ≥85% below | AS bucket 07 | 169 | 81 | 47.9% | 38 | 22.5% |
| Gap ≥20% | AC >= 20 (or AD 05–06) | 524 | 188 | 35.9% | 89 | 17.0% |
| Revenue surprise ≥15% | Q >= 15 (or R 07) | 822 | 260 | 31.6% | 91 | 11.1% |
| 10M Green | BN = "Green" | 4,135 | 1,036 | 25.1% | 307 | 7.4% |
| 60M Green | CF = "Green" | 4,098 | 1,030 | 25.1% | 299 | 7.3% |
| 60M RVOL ≥2.5x | CH >= 2.5 | 695 | 204 | 29.4% | 79 | 11.4% |
| ADR≥5 + 10M Green + 10M RVOL≥0.45 | AE>=5; BN=Green; BP>=0.45 | 301 | 145 | 48.2% | 69 | 22.9% |

### 15.4 Excel COUNTIFS examples
Raw-row formulas below will include the six excess duplicate rows unless you also filter/use a Unique Event helper. They are useful as a fast sanity check:
```excel
6M mature raw N:
=COUNTIFS($A:$A,"<="&DATE(2026,2,21))

6M ADR>=5 and 50%+ raw count:
=COUNTIFS($A:$A,"<="&DATE(2026,2,21),$AE:$AE,">=5",$DB:$DB,">=0.5")

6M ADR>=5 and 100%+ raw count:
=COUNTIFS($A:$A,"<="&DATE(2026,2,21),$AE:$AE,">=5",$DB:$DB,">=1")

6M ADR>=5 + 10M Green + 10M RVOL>=0.45 and 50%+ raw count:
=COUNTIFS($A:$A,"<="&DATE(2026,2,21),$AE:$AE,">=5",$BN:$BN,"Green",$BP:$BP,">=0.45",$DB:$DB,">=0.5")
```

### 15.5 ATH warning
Do **not** use `ABS(AR)` to define deep drawdown without handling the ATH sentinel: `AR=1` means “At ATH,” not 100% below ATH. The safest verification is to use the existing category in column AS.

### 15.6 Market-regime verification
Column H `Era` has now been corrected to use the **reaction year**, so it can be used for era pivots. For an independent audit, create `Reaction Year =YEAR(A2)` and verify that column H maps each reaction year into the same era buckets shown in §3.2. The report’s regime statistics were calculated from `reaction_date`, so they are unchanged by this workbook-formula correction.

---

## 16. Appendix A — 1M and 3M factor tables

### 1M tables
#### ADR
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| 2-3% | 3,017 | 2,062 / 68.3% | 30 / 1.0% | 5 / 0.2% | 0 / 0.0% | 6.6% | 0.06 | 0.00 |
| 02 \| 3-4% | 2,428 | 1,351 / 55.6% | 95 / 3.9% | 18 / 0.7% | 1 / 0.0% | 8.8% | 0.26 | 0.12 |
| 03 \| 4-5% | 1,513 | 679 / 44.9% | 169 / 11.2% | 33 / 2.2% | 6 / 0.4% | 11.3% | 0.77 | 1.14 |
| 04 \| 5-7% | 1,398 | 539 / 38.6% | 267 / 19.1% | 82 / 5.9% | 9 / 0.6% | 13.6% | 2.06 | 1.85 |
| 05 \| 7-10% | 574 | 195 / 34.0% | 154 / 26.8% | 72 / 12.5% | 7 / 1.2% | 16.1% | 4.40 | 3.50 |
| 06 \| 10%+ | 263 | 79 / 30.0% | 103 / 39.2% | 52 / 19.8% | 9 / 3.4% | 21.7% | 6.94 | 9.83 |

#### Dollar Turnover
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <0.5% | 879 | 517 / 58.8% | 47 / 5.3% | 17 / 1.9% | 2 / 0.2% | 8.3% | 0.68 | 0.65 |
| 02 \| 0.5-1% | 2,975 | 1,743 / 58.6% | 133 / 4.5% | 28 / 0.9% | 3 / 0.1% | 8.1% | 0.33 | 0.29 |
| 03 \| 1-2% | 3,484 | 1,869 / 53.6% | 301 / 8.6% | 74 / 2.1% | 9 / 0.3% | 9.2% | 0.75 | 0.74 |
| 04 \| 2-5% | 1,591 | 685 / 43.1% | 259 / 16.3% | 108 / 6.8% | 11 / 0.7% | 11.9% | 2.38 | 1.99 |
| 05 \| 5-10% | 207 | 71 / 34.3% | 58 / 28.0% | 25 / 12.1% | 4 / 1.9% | 15.7% | 4.24 | 5.55 |
| 06 \| 10%+ | 57 | 20 / 35.1% | 20 / 35.1% | 10 / 17.5% | 3 / 5.3% | 17.1% | 6.16 | 15.12 |

#### Market Cap
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <$1B | 655 | 261 / 39.8% | 153 / 23.4% | 69 / 10.5% | 11 / 1.7% | 13.9% | 3.70 | 4.82 |
| 02 \| $1-2B | 1,692 | 842 / 49.8% | 205 / 12.1% | 59 / 3.5% | 6 / 0.4% | 10.1% | 1.22 | 1.02 |
| 03 \| $2-5B | 2,837 | 1,480 / 52.2% | 225 / 7.9% | 68 / 2.4% | 8 / 0.3% | 9.5% | 0.84 | 0.81 |
| 04 \| $5-10B | 1,599 | 895 / 56.0% | 97 / 6.1% | 27 / 1.7% | 5 / 0.3% | 8.6% | 0.59 | 0.90 |
| 05 \| $10-25B | 1,277 | 736 / 57.6% | 72 / 5.6% | 21 / 1.6% | 1 / 0.1% | 8.1% | 0.58 | 0.22 |
| 06 \| $25-100B | 853 | 502 / 58.9% | 52 / 6.1% | 13 / 1.5% | 1 / 0.1% | 7.9% | 0.53 | 0.34 |
| 07 \| $100B+ | 280 | 189 / 67.5% | 14 / 5.0% | 5 / 1.8% | 0 / 0.0% | 6.9% | 0.63 | 0.00 |

#### ATH
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| At ATH | 1,418 | 769 / 54.2% | 111 / 7.8% | 40 / 2.8% | 4 / 0.3% | 9.1% | 0.99 | 0.81 |
| 02 \| 0-10% below | 1,495 | 882 / 59.0% | 79 / 5.3% | 18 / 1.2% | 5 / 0.3% | 7.9% | 0.42 | 0.96 |
| 03 \| 10-25% below | 2,045 | 1,265 / 61.9% | 109 / 5.3% | 35 / 1.7% | 4 / 0.2% | 7.5% | 0.60 | 0.56 |
| 04 \| 25-50% below | 2,493 | 1,320 / 52.9% | 185 / 7.4% | 50 / 2.0% | 6 / 0.2% | 9.3% | 0.70 | 0.69 |
| 05 \| 50-70% below | 1,108 | 458 / 41.3% | 165 / 14.9% | 49 / 4.4% | 4 / 0.4% | 12.2% | 1.55 | 1.04 |
| 06 \| 70-85% below | 463 | 156 / 33.7% | 110 / 23.8% | 38 / 8.2% | 2 / 0.4% | 16.8% | 2.88 | 1.24 |
| 07 \| 85%+ below | 171 | 55 / 32.2% | 59 / 34.5% | 32 / 18.7% | 7 / 4.1% | 20.1% | 6.57 | 11.76 |

#### Gap
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| 5-7.5% | 3,733 | 2,131 / 57.1% | 251 / 6.7% | 61 / 1.6% | 2 / 0.1% | 8.4% | 0.57 | 0.15 |
| 02 \| 7.5-10% | 2,120 | 1,154 / 54.4% | 157 / 7.4% | 45 / 2.1% | 10 / 0.5% | 9.0% | 0.74 | 1.36 |
| 03 \| 10-15% | 1,950 | 1,017 / 52.2% | 184 / 9.4% | 63 / 3.2% | 10 / 0.5% | 9.5% | 1.13 | 1.47 |
| 04 \| 15-20% | 790 | 368 / 46.6% | 103 / 13.0% | 28 / 3.5% | 2 / 0.3% | 11.0% | 1.24 | 0.73 |
| 05 \| 20-30% | 480 | 189 / 39.4% | 85 / 17.7% | 43 / 9.0% | 4 / 0.8% | 13.3% | 3.14 | 2.39 |
| 06 \| 30%+ | 120 | 46 / 38.3% | 38 / 31.7% | 22 / 18.3% | 4 / 3.3% | 14.3% | 6.43 | 9.58 |

#### IPO Age
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <1 year | 370 | 158 / 42.7% | 69 / 18.6% | 31 / 8.4% | 3 / 0.8% | 12.4% | 2.94 | 2.33 |
| 02 \| 1-3 years | 929 | 412 / 44.3% | 121 / 13.0% | 34 / 3.7% | 3 / 0.3% | 11.9% | 1.28 | 0.93 |
| 03 \| 3-5 years | 1,006 | 477 / 47.4% | 131 / 13.0% | 42 / 4.2% | 5 / 0.5% | 10.5% | 1.46 | 1.43 |
| 04 \| 5-10 years | 1,552 | 827 / 53.3% | 145 / 9.3% | 46 / 3.0% | 9 / 0.6% | 9.4% | 1.04 | 1.67 |
| 05 \| 10-20 years | 1,723 | 958 / 55.6% | 142 / 8.2% | 44 / 2.6% | 4 / 0.2% | 8.6% | 0.90 | 0.67 |
| 06 \| 20+ years | 3,478 | 2,010 / 57.8% | 193 / 5.5% | 62 / 1.8% | 8 / 0.2% | 8.3% | 0.63 | 0.66 |

#### Dollar Volume
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| $10-25M | 2,877 | 1,470 / 51.1% | 315 / 10.9% | 98 / 3.4% | 14 / 0.5% | 9.7% | 1.20 | 1.40 |
| 02 \| $25-50M | 1,903 | 971 / 51.0% | 180 / 9.5% | 59 / 3.1% | 9 / 0.5% | 9.7% | 1.09 | 1.36 |
| 03 \| $50-100M | 1,634 | 896 / 54.8% | 114 / 7.0% | 37 / 2.3% | 1 / 0.1% | 8.9% | 0.79 | 0.18 |
| 04 \| $100-250M | 1,487 | 839 / 56.4% | 100 / 6.7% | 36 / 2.4% | 6 / 0.4% | 8.5% | 0.85 | 1.16 |
| 05 \| $250M-1B | 1,021 | 576 / 56.4% | 81 / 7.9% | 23 / 2.3% | 2 / 0.2% | 8.4% | 0.79 | 0.56 |
| 06 \| $1B+ | 271 | 153 / 56.5% | 28 / 10.3% | 9 / 3.3% | 0 / 0.0% | 8.3% | 1.17 | 0.00 |

#### EPS Surprise
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Miss (<0%) | 1,028 | 504 / 49.0% | 136 / 13.2% | 40 / 3.9% | 9 / 0.9% | 10.2% | 1.36 | 2.51 |
| 02 \| 0-5% | 891 | 554 / 62.2% | 49 / 5.5% | 26 / 2.9% | 2 / 0.2% | 7.6% | 1.02 | 0.64 |
| 03 \| 5-15% | 1,703 | 1,044 / 61.3% | 80 / 4.7% | 19 / 1.1% | 2 / 0.1% | 7.6% | 0.39 | 0.34 |
| 04 \| 15-30% | 1,676 | 917 / 54.7% | 114 / 6.8% | 31 / 1.8% | 1 / 0.1% | 8.8% | 0.65 | 0.17 |
| 05 \| 30-70% | 1,737 | 872 / 50.2% | 158 / 9.1% | 48 / 2.8% | 8 / 0.5% | 10.0% | 0.97 | 1.32 |
| 06 \| 70-150% | 903 | 426 / 47.2% | 106 / 11.7% | 33 / 3.7% | 3 / 0.3% | 10.7% | 1.28 | 0.95 |
| 07 \| 150%+ | 819 | 369 / 45.1% | 118 / 14.4% | 39 / 4.8% | 1 / 0.1% | 11.0% | 1.67 | 0.35 |

#### Revenue Surprise
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Miss (<0%) | 1,313 | 704 / 53.6% | 136 / 10.4% | 51 / 3.9% | 9 / 0.7% | 9.1% | 1.36 | 1.97 |
| 02 \| 0-0.5% | 460 | 271 / 58.9% | 26 / 5.7% | 7 / 1.5% | 0 / 0.0% | 8.0% | 0.53 | 0.00 |
| 03 \| 0.5-2.25% | 1,784 | 1,067 / 59.8% | 88 / 4.9% | 28 / 1.6% | 3 / 0.2% | 7.8% | 0.55 | 0.48 |
| 04 \| 2.25-4.5% | 1,753 | 1,015 / 57.9% | 99 / 5.6% | 25 / 1.4% | 6 / 0.3% | 8.2% | 0.50 | 0.98 |
| 05 \| 4.5-8.5% | 1,591 | 813 / 51.1% | 147 / 9.2% | 40 / 2.5% | 2 / 0.1% | 9.7% | 0.88 | 0.36 |
| 06 \| 8.5-15% | 973 | 448 / 46.0% | 109 / 11.2% | 36 / 3.7% | 2 / 0.2% | 11.0% | 1.30 | 0.59 |
| 07 \| 15%+ | 884 | 386 / 43.7% | 138 / 15.6% | 46 / 5.2% | 2 / 0.2% | 11.7% | 1.83 | 0.65 |

#### Surprise Matrix
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Both Big Beats | 570 | 246 / 43.2% | 91 / 16.0% | 33 / 5.8% | 1 / 0.2% | 11.8% | 2.03 | 0.50 |
| 02 \| Big EPS + Revenue Beat | 2,551 | 1,257 / 49.3% | 245 / 9.6% | 70 / 2.7% | 8 / 0.3% | 10.1% | 0.96 | 0.90 |
| 03 \| Big EPS Beat + Revenue Miss | 310 | 153 / 49.4% | 39 / 12.6% | 15 / 4.8% | 2 / 0.6% | 10.3% | 1.70 | 1.85 |
| 04 \| EPS Beat + Big Revenue Beat | 180 | 83 / 46.1% | 24 / 13.3% | 8 / 4.4% | 0 / 0.0% | 11.1% | 1.56 | 0.00 |
| 05 \| Both Positive, Neither Big | 3,377 | 2,022 / 59.9% | 163 / 4.8% | 47 / 1.4% | 2 / 0.1% | 7.8% | 0.49 | 0.17 |
| 06 \| EPS Beat + Revenue Miss | 646 | 378 / 58.5% | 45 / 7.0% | 16 / 2.5% | 2 / 0.3% | 8.4% | 0.87 | 0.89 |
| 07 \| EPS Miss + Big Revenue Beat | 107 | 43 / 40.2% | 20 / 18.7% | 3 / 2.8% | 1 / 0.9% | 15.3% | 0.98 | 2.68 |
| 08 \| EPS Miss + Revenue Beat | 547 | 289 / 52.8% | 55 / 10.1% | 15 / 2.7% | 3 / 0.5% | 9.4% | 0.96 | 1.58 |
| 09 \| Both Miss | 325 | 156 / 48.0% | 48 / 14.8% | 19 / 5.8% | 5 / 1.5% | 10.6% | 2.05 | 4.42 |

#### EPS YoY
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Profit -> Loss | 240 | 103 / 42.9% | 40 / 16.7% | 15 / 6.2% | 3 / 1.2% | 12.1% | 2.19 | 3.59 |
| 02 \| Loss Worsening | 417 | 167 / 40.0% | 82 / 19.7% | 25 / 6.0% | 5 / 1.2% | 12.9% | 2.10 | 3.44 |
| 03 \| Loss Narrowing | 841 | 340 / 40.4% | 163 / 19.4% | 67 / 8.0% | 12 / 1.4% | 13.2% | 2.79 | 4.10 |
| 04 \| Loss -> Profit | 754 | 368 / 48.8% | 111 / 14.7% | 38 / 5.0% | 3 / 0.4% | 10.2% | 1.77 | 1.14 |
| 05 \| Positive EPS Decline | 1,661 | 896 / 53.9% | 119 / 7.2% | 26 / 1.6% | 2 / 0.1% | 9.0% | 0.55 | 0.35 |
| 06 \| EPS Growth 0-25% | 1,763 | 1,087 / 61.7% | 59 / 3.3% | 16 / 0.9% | 2 / 0.1% | 7.7% | 0.32 | 0.33 |
| 07 \| EPS Growth 25-50% | 1,189 | 726 / 61.1% | 41 / 3.4% | 7 / 0.6% | 0 / 0.0% | 7.8% | 0.21 | 0.00 |
| 08 \| EPS Growth 50-100% | 807 | 456 / 56.5% | 43 / 5.3% | 12 / 1.5% | 1 / 0.1% | 8.7% | 0.52 | 0.36 |
| 09 \| EPS Growth 100%+ | 1,010 | 511 / 50.6% | 88 / 8.7% | 22 / 2.2% | 0 / 0.0% | 9.8% | 0.76 | 0.00 |

#### Rev YoY
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Negative | 1,836 | 947 / 51.6% | 196 / 10.7% | 62 / 3.4% | 11 / 0.6% | 9.6% | 1.18 | 1.72 |
| 02 \| 0-10% | 1,939 | 1,139 / 58.7% | 98 / 5.1% | 34 / 1.8% | 4 / 0.2% | 8.2% | 0.62 | 0.59 |
| 03 \| 10-20% | 1,575 | 944 / 59.9% | 98 / 6.2% | 29 / 1.8% | 6 / 0.4% | 7.9% | 0.65 | 1.09 |
| 04 \| 20-35% | 1,376 | 748 / 54.4% | 86 / 6.2% | 20 / 1.5% | 0 / 0.0% | 8.9% | 0.51 | 0.00 |
| 05 \| 35-100% | 1,394 | 639 / 45.8% | 168 / 12.1% | 44 / 3.2% | 4 / 0.3% | 11.3% | 1.11 | 0.82 |
| 06 \| 100%+ | 528 | 221 / 41.9% | 93 / 17.6% | 40 / 7.6% | 2 / 0.4% | 12.3% | 2.66 | 1.09 |

#### SPY
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Green | 5,195 | 2,799 / 53.9% | 468 / 9.0% | 147 / 2.8% | 18 / 0.3% | 9.1% | 0.99 | 1.00 |
| 02 \| Light Green | 312 | 166 / 53.2% | 28 / 9.0% | 7 / 2.2% | 1 / 0.3% | 9.2% | 0.79 | 0.92 |
| 03 \| Yellow | 137 | 75 / 54.7% | 7 / 5.1% | 2 / 1.5% | 1 / 0.7% | 8.4% | 0.51 | 2.10 |
| 04 \| Downtrend | 3,549 | 1,865 / 52.6% | 315 / 8.9% | 106 / 3.0% | 12 / 0.3% | 9.4% | 1.05 | 0.97 |

### 3M tables
#### ADR
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| 2-3% | 2,998 | 1,275 / 42.5% | 309 / 10.3% | 56 / 1.9% | 4 / 0.1% | 12.1% | 0.17 | 0.06 |
| 02 \| 3-4% | 2,414 | 779 / 32.3% | 515 / 21.3% | 158 / 6.5% | 11 / 0.5% | 16.1% | 0.60 | 0.20 |
| 03 \| 4-5% | 1,496 | 368 / 24.6% | 537 / 35.9% | 218 / 14.6% | 33 / 2.2% | 21.1% | 1.33 | 0.98 |
| 04 \| 5-7% | 1,384 | 333 / 24.1% | 581 / 42.0% | 303 / 21.9% | 75 / 5.4% | 24.0% | 2.00 | 2.41 |
| 05 \| 7-10% | 570 | 121 / 21.2% | 266 / 46.7% | 172 / 30.2% | 48 / 8.4% | 28.3% | 2.75 | 3.75 |
| 06 \| 10%+ | 261 | 63 / 24.1% | 143 / 54.8% | 94 / 36.0% | 34 / 13.0% | 33.6% | 3.28 | 5.80 |

#### Dollar Turnover
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <0.5% | 877 | 324 / 36.9% | 159 / 18.1% | 55 / 6.3% | 7 / 0.8% | 13.6% | 0.57 | 0.36 |
| 02 \| 0.5-1% | 2,962 | 1,070 / 36.1% | 553 / 18.7% | 179 / 6.0% | 27 / 0.9% | 14.5% | 0.55 | 0.41 |
| 03 \| 1-2% | 3,455 | 1,088 / 31.5% | 935 / 27.1% | 387 / 11.2% | 67 / 1.9% | 17.0% | 1.02 | 0.86 |
| 04 \| 2-5% | 1,569 | 396 / 25.2% | 574 / 36.6% | 291 / 18.5% | 71 / 4.5% | 21.6% | 1.69 | 2.01 |
| 05 \| 5-10% | 203 | 47 / 23.2% | 98 / 48.3% | 70 / 34.5% | 24 / 11.8% | 28.3% | 3.14 | 5.26 |
| 06 \| 10%+ | 57 | 14 / 24.6% | 32 / 56.1% | 19 / 33.3% | 9 / 15.8% | 35.5% | 3.04 | 7.03 |

#### Market Cap
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <$1B | 647 | 149 / 23.0% | 293 / 45.3% | 165 / 25.5% | 58 / 9.0% | 25.7% | 2.32 | 3.99 |
| 02 \| $1-2B | 1,679 | 512 / 30.5% | 500 / 29.8% | 239 / 14.2% | 46 / 2.7% | 18.0% | 1.30 | 1.22 |
| 03 \| $2-5B | 2,823 | 909 / 32.2% | 699 / 24.8% | 286 / 10.1% | 51 / 1.8% | 16.4% | 0.92 | 0.80 |
| 04 \| $5-10B | 1,592 | 527 / 33.1% | 362 / 22.7% | 121 / 7.6% | 20 / 1.3% | 15.8% | 0.69 | 0.56 |
| 05 \| $10-25B | 1,268 | 429 / 33.8% | 281 / 22.2% | 106 / 8.4% | 15 / 1.2% | 15.4% | 0.76 | 0.53 |
| 06 \| $25-100B | 839 | 297 / 35.4% | 170 / 20.3% | 68 / 8.1% | 13 / 1.5% | 14.5% | 0.74 | 0.69 |
| 07 \| $100B+ | 275 | 116 / 42.2% | 46 / 16.7% | 16 / 5.8% | 2 / 0.7% | 12.3% | 0.53 | 0.32 |

#### ATH
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| At ATH | 1,409 | 448 / 31.8% | 330 / 23.4% | 144 / 10.2% | 31 / 2.2% | 16.1% | 0.93 | 0.98 |
| 02 \| 0-10% below | 1,485 | 543 / 36.6% | 287 / 19.3% | 102 / 6.9% | 22 / 1.5% | 14.3% | 0.63 | 0.66 |
| 03 \| 10-25% below | 2,025 | 778 / 38.4% | 383 / 18.9% | 161 / 8.0% | 27 / 1.3% | 13.9% | 0.72 | 0.59 |
| 04 \| 25-50% below | 2,477 | 806 / 32.5% | 630 / 25.4% | 234 / 9.4% | 37 / 1.5% | 16.4% | 0.86 | 0.66 |
| 05 \| 50-70% below | 1,095 | 241 / 22.0% | 414 / 37.8% | 178 / 16.3% | 34 / 3.1% | 23.0% | 1.48 | 1.38 |
| 06 \| 70-85% below | 461 | 90 / 19.5% | 213 / 46.2% | 111 / 24.1% | 24 / 5.2% | 27.0% | 2.19 | 2.32 |
| 07 \| 85%+ below | 171 | 33 / 19.3% | 94 / 55.0% | 71 / 41.5% | 30 / 17.5% | 34.4% | 3.78 | 7.81 |

#### Gap
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| 5-7.5% | 3,711 | 1,292 / 34.8% | 824 / 22.2% | 309 / 8.3% | 46 / 1.2% | 14.9% | 0.76 | 0.55 |
| 02 \| 7.5-10% | 2,110 | 664 / 31.5% | 475 / 22.5% | 194 / 9.2% | 40 / 1.9% | 16.1% | 0.84 | 0.84 |
| 03 \| 10-15% | 1,934 | 612 / 31.6% | 540 / 27.9% | 247 / 12.8% | 58 / 3.0% | 17.0% | 1.16 | 1.33 |
| 04 \| 15-20% | 779 | 227 / 29.1% | 257 / 33.0% | 112 / 14.4% | 17 / 2.2% | 19.9% | 1.31 | 0.97 |
| 05 \| 20-30% | 474 | 112 / 23.6% | 199 / 42.0% | 103 / 21.7% | 28 / 5.9% | 24.7% | 1.98 | 2.63 |
| 06 \| 30%+ | 115 | 32 / 27.8% | 56 / 48.7% | 36 / 31.3% | 16 / 13.9% | 29.6% | 2.85 | 6.19 |

#### IPO Age
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| <1 year | 369 | 100 / 27.1% | 135 / 36.6% | 78 / 21.1% | 16 / 4.3% | 20.7% | 1.93 | 1.93 |
| 02 \| 1-3 years | 926 | 258 / 27.9% | 311 / 33.6% | 150 / 16.2% | 30 / 3.2% | 19.5% | 1.48 | 1.44 |
| 03 \| 3-5 years | 1,006 | 302 / 30.0% | 308 / 30.6% | 143 / 14.2% | 34 / 3.4% | 18.2% | 1.30 | 1.50 |
| 04 \| 5-10 years | 1,539 | 476 / 30.9% | 447 / 29.0% | 178 / 11.6% | 36 / 2.3% | 17.4% | 1.05 | 1.04 |
| 05 \| 10-20 years | 1,715 | 572 / 33.4% | 413 / 24.1% | 159 / 9.3% | 34 / 2.0% | 15.9% | 0.84 | 0.88 |
| 06 \| 20+ years | 3,433 | 1,187 / 34.6% | 698 / 20.3% | 277 / 8.1% | 53 / 1.5% | 14.8% | 0.74 | 0.69 |

#### Dollar Volume
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| $10-25M | 2,861 | 903 / 31.6% | 798 / 27.9% | 362 / 12.7% | 84 / 2.9% | 17.3% | 1.15 | 1.31 |
| 02 \| $25-50M | 1,894 | 609 / 32.2% | 506 / 26.7% | 221 / 11.7% | 47 / 2.5% | 17.4% | 1.06 | 1.10 |
| 03 \| $50-100M | 1,623 | 518 / 31.9% | 402 / 24.8% | 145 / 8.9% | 19 / 1.2% | 15.4% | 0.81 | 0.52 |
| 04 \| $100-250M | 1,475 | 488 / 33.1% | 334 / 22.6% | 134 / 9.1% | 28 / 1.9% | 15.5% | 0.83 | 0.84 |
| 05 \| $250M-1B | 1,005 | 327 / 32.5% | 235 / 23.4% | 105 / 10.4% | 18 / 1.8% | 15.5% | 0.95 | 0.80 |
| 06 \| $1B+ | 265 | 94 / 35.5% | 76 / 28.7% | 34 / 12.8% | 9 / 3.4% | 15.7% | 1.17 | 1.51 |

#### EPS Surprise
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Miss (<0%) | 1,021 | 309 / 30.3% | 332 / 32.5% | 152 / 14.9% | 28 / 2.7% | 19.1% | 1.36 | 1.22 |
| 02 \| 0-5% | 884 | 339 / 38.3% | 154 / 17.4% | 71 / 8.0% | 13 / 1.5% | 13.1% | 0.73 | 0.65 |
| 03 \| 5-15% | 1,688 | 637 / 37.7% | 315 / 18.7% | 107 / 6.3% | 15 / 0.9% | 13.6% | 0.58 | 0.40 |
| 04 \| 15-30% | 1,663 | 536 / 32.2% | 380 / 22.9% | 148 / 8.9% | 29 / 1.7% | 16.0% | 0.81 | 0.78 |
| 05 \| 30-70% | 1,721 | 514 / 29.9% | 476 / 27.7% | 219 / 12.7% | 51 / 3.0% | 17.5% | 1.16 | 1.32 |
| 06 \| 70-150% | 898 | 251 / 28.0% | 290 / 32.3% | 130 / 14.5% | 22 / 2.4% | 18.6% | 1.32 | 1.09 |
| 07 \| 150%+ | 812 | 225 / 27.7% | 278 / 34.2% | 114 / 14.0% | 32 / 3.9% | 20.2% | 1.28 | 1.75 |

#### Revenue Surprise
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Miss (<0%) | 1,310 | 415 / 31.7% | 340 / 26.0% | 156 / 11.9% | 40 / 3.1% | 16.5% | 1.09 | 1.36 |
| 02 \| 0-0.5% | 454 | 159 / 35.0% | 90 / 19.8% | 27 / 5.9% | 2 / 0.4% | 14.6% | 0.54 | 0.20 |
| 03 \| 0.5-2.25% | 1,762 | 627 / 35.6% | 333 / 18.9% | 128 / 7.3% | 29 / 1.6% | 14.2% | 0.66 | 0.73 |
| 04 \| 2.25-4.5% | 1,741 | 632 / 36.3% | 382 / 21.9% | 154 / 8.8% | 23 / 1.3% | 14.4% | 0.81 | 0.59 |
| 05 \| 4.5-8.5% | 1,581 | 475 / 30.0% | 440 / 27.8% | 180 / 11.4% | 26 / 1.6% | 17.3% | 1.04 | 0.73 |
| 06 \| 8.5-15% | 962 | 264 / 27.4% | 302 / 31.4% | 140 / 14.6% | 26 / 2.7% | 19.1% | 1.33 | 1.20 |
| 07 \| 15%+ | 878 | 241 / 27.4% | 326 / 37.1% | 148 / 16.9% | 38 / 4.3% | 21.6% | 1.54 | 1.93 |

#### Surprise Matrix
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Both Big Beats | 567 | 152 / 26.8% | 223 / 39.3% | 102 / 18.0% | 28 / 4.9% | 22.8% | 1.64 | 2.20 |
| 02 \| Big EPS + Revenue Beat | 2,526 | 754 / 29.8% | 730 / 28.9% | 316 / 12.5% | 61 / 2.4% | 17.5% | 1.14 | 1.07 |
| 03 \| Big EPS Beat + Revenue Miss | 310 | 79 / 25.5% | 82 / 26.5% | 38 / 12.3% | 15 / 4.8% | 19.0% | 1.12 | 2.15 |
| 04 \| EPS Beat + Big Revenue Beat | 178 | 51 / 28.7% | 55 / 30.9% | 27 / 15.2% | 6 / 3.4% | 17.7% | 1.38 | 1.50 |
| 05 \| Both Positive, Neither Big | 3,347 | 1,207 / 36.1% | 632 / 18.9% | 234 / 7.0% | 36 / 1.1% | 14.2% | 0.64 | 0.48 |
| 06 \| EPS Beat + Revenue Miss | 643 | 232 / 36.1% | 144 / 22.4% | 55 / 8.6% | 9 / 1.4% | 14.2% | 0.78 | 0.62 |
| 07 \| EPS Miss + Big Revenue Beat | 106 | 30 / 28.3% | 42 / 39.6% | 16 / 15.1% | 4 / 3.8% | 24.4% | 1.38 | 1.68 |
| 08 \| EPS Miss + Revenue Beat | 541 | 172 / 31.8% | 164 / 30.3% | 70 / 12.9% | 9 / 1.7% | 17.8% | 1.18 | 0.74 |
| 09 \| Both Miss | 325 | 93 / 28.6% | 104 / 32.0% | 57 / 17.5% | 15 / 4.6% | 19.3% | 1.60 | 2.05 |

#### EPS YoY
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Profit -> Loss | 239 | 57 / 23.8% | 94 / 39.3% | 58 / 24.3% | 13 / 5.4% | 22.7% | 2.21 | 2.42 |
| 02 \| Loss Worsening | 417 | 114 / 27.3% | 162 / 38.8% | 93 / 22.3% | 20 / 4.8% | 21.9% | 2.03 | 2.13 |
| 03 \| Loss Narrowing | 838 | 209 / 24.9% | 350 / 41.8% | 191 / 22.8% | 63 / 7.5% | 24.5% | 2.08 | 3.34 |
| 04 \| Loss -> Profit | 750 | 229 / 30.5% | 242 / 32.3% | 117 / 15.6% | 31 / 4.1% | 19.3% | 1.42 | 1.84 |
| 05 \| Positive EPS Decline | 1,649 | 536 / 32.5% | 406 / 24.6% | 142 / 8.6% | 12 / 0.7% | 16.4% | 0.79 | 0.32 |
| 06 \| EPS Growth 0-25% | 1,747 | 637 / 36.5% | 294 / 16.8% | 82 / 4.7% | 10 / 0.6% | 13.5% | 0.43 | 0.25 |
| 07 \| EPS Growth 25-50% | 1,176 | 401 / 34.1% | 223 / 19.0% | 65 / 5.5% | 4 / 0.3% | 15.0% | 0.50 | 0.15 |
| 08 \| EPS Growth 50-100% | 796 | 283 / 35.6% | 151 / 19.0% | 56 / 7.0% | 13 / 1.6% | 14.1% | 0.64 | 0.73 |
| 09 \| EPS Growth 100%+ | 1,001 | 314 / 31.4% | 280 / 28.0% | 115 / 11.5% | 21 / 2.1% | 16.6% | 1.05 | 0.93 |

#### Rev YoY
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Negative | 1,823 | 561 / 30.8% | 502 / 27.5% | 224 / 12.3% | 48 / 2.6% | 17.1% | 1.12 | 1.17 |
| 02 \| 0-10% | 1,919 | 651 / 33.9% | 397 / 20.7% | 132 / 6.9% | 22 / 1.1% | 14.7% | 0.63 | 0.51 |
| 03 \| 10-20% | 1,557 | 571 / 36.7% | 329 / 21.1% | 127 / 8.2% | 25 / 1.6% | 14.3% | 0.74 | 0.71 |
| 04 \| 20-35% | 1,366 | 438 / 32.1% | 328 / 24.0% | 127 / 9.3% | 16 / 1.2% | 16.2% | 0.85 | 0.52 |
| 05 \| 35-100% | 1,388 | 406 / 29.3% | 450 / 32.4% | 194 / 14.0% | 39 / 2.8% | 19.3% | 1.27 | 1.25 |
| 06 \| 100%+ | 525 | 140 / 26.7% | 188 / 35.8% | 114 / 21.7% | 31 / 5.9% | 21.2% | 1.98 | 2.63 |

#### SPY
| Bucket | N | <10% | 30%+ | 50%+ | 100%+ | Median MFE | 50% lift | 100% lift |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 01 \| Green | 5,144 | 1,690 / 32.9% | 1,278 / 24.8% | 536 / 10.4% | 111 / 2.2% | 16.0% | 0.95 | 0.96 |
| 02 \| Light Green | 311 | 100 / 32.2% | 90 / 28.9% | 39 / 12.5% | 5 / 1.6% | 17.9% | 1.14 | 0.72 |
| 03 \| Yellow | 134 | 49 / 36.6% | 29 / 21.6% | 15 / 11.2% | 2 / 1.5% | 14.9% | 1.02 | 0.66 |
| 04 \| Downtrend | 3,534 | 1,100 / 31.1% | 954 / 27.0% | 411 / 11.6% | 87 / 2.5% | 16.8% | 1.06 | 1.10 |

---

## 17. Appendix B — full workbook column dictionary

| Column | Header |
| :--- | :--- |
| A | reaction_date |
| B | ticker |
| C | company_name |
| D | SectorCode |
| E | IndCode |
| F | fiscal_period |
| G | fiscal_year |
| H | Era (reaction-year based) |
| I | release_time |
| J | release_timing |
| K | actual_eps |
| L | estimated_eps |
| M | eps_surprise_percent |
| N | EPS Surprise Category |
| O | actual_revenue |
| P | estimated_revenue |
| Q | revenue_surprise_percent |
| R | Revenue Surprise % Category |
| S | Revenue EPS Surprise Combo |
| T | EPS YoY Category |
| U | Revenue YoY Category |
| V | TTM EPS Growth % |
| W | TTM Revenue Growth % |
| X | Dividend Yield % |
| Y | 4-Week Price Change % |
| Z | Gap Day Open |
| AA | Gap Day Close |
| AB | Gap Day Green/Red? |
| AC | gap_pct |
| AD | Gap % Category |
| AE | adr14 |
| AF | ADR Category |
| AG | pre_gap_market_cap |
| AH | Mkt Cap Category |
| AI | avg_share_volume_30d |
| AJ | dollar_volume_proxy_30d |
| AK | Pre-Gap 30D Avg Dollar Volume |
| AL | Pre-Gap 30D Avg Share Volume |
| AM | Pregap 30D avg Dollar Volume Category |
| AN | Pre-Gap 100D Avg Dollar Volume |
| AO | Pre-Gap 100D Avg Share Volume |
| AP | Prior ATH Price |
| AQ | Prior ATH Date |
| AR | % from ATH |
| AS | ATH Category |
| AT | IPO Date |
| AU | IPO Date Category |
| AV | SPY Trend Color |
| AW | Gap Day Total Volume |
| AX | Gap Day Total Dollar Volume |
| AY | Relative Volume Multiple (Whole Day vs 30D Avg) |
| AZ | Whole Day Relative Volume Category |
| BA | 1M Candle Close |
| BB | 1M Candle Green/Red? |
| BC | 1M Candle Volume |
| BD | 1M Candle Relative Volume 30D |
| BE | 1M Candle Dollar Volume |
| BF | 1M Volume Category |
| BG | 5M Candle Close |
| BH | 5M Candle Green/Red? |
| BI | 5M Candle Volume |
| BJ | 5M Candle Relative Volume 30D |
| BK | 5M Candle Dollar Volume |
| BL | 5M Volume Category |
| BM | 10M Candle Close |
| BN | 10M Candle Green/Red? |
| BO | 10M Candle Volume |
| BP | 10M Candle Relative Volume 30D |
| BQ | 10M Candle Dollar Volume |
| BR | 10M Volume Category |
| BS | 15M Candle Close |
| BT | 15M Candle Green/Red? |
| BU | 15M Candle Volume |
| BV | 15M Candle Relative Volume 30D |
| BW | 15M Candle Dollar Volume |
| BX | 15M Volume Category |
| BY | 30M Candle Close |
| BZ | 30M Candle Green/Red? |
| CA | 30M Candle Volume |
| CB | 30M Candle Relative Volume 30D |
| CC | 30M Candle Dollar Volume |
| CD | 30M Volume Category |
| CE | 60M Candle Close |
| CF | 60M Candle Green/Red? |
| CG | 60M Candle Volume |
| CH | 60M Candle Relative Volume 30D |
| CI | 60M Candle Dollar Volume |
| CJ | 60M Volume Category |
| CK | 1M High |
| CL | 1M High Date |
| CM | 1M High % |
| CN | 1M High % Category |
| CO | 1M Close |
| CP | 1M Close Date |
| CQ | 1M Close Performance % |
| CR | 3M High |
| CS | 3M High Date |
| CT | 3M High % |
| CU | 3M High % Category |
| CV | 3M Close |
| CW | 3M Close Date |
| CX | 3M Close Performance % |
| CY | 3M Close Performance Category |
| CZ | 6M High |
| DA | 6M High Date |
| DB | 6M High % |
| DC | 6M High % Category |
| DD | 6M Close |
| DE | 6M Close Date |
| DF | 6M Close Performance % |
| DG | Trading Turnover % |
| DH | Trading Turnover % Category |
| DI | 1M High Same Day? |
| DJ | 3M High Same Day? |
| DK | 6M High Same Day? |

---

## 18. Final research verdict

The full-history dataset changes the interpretation in a useful way. The core EP thesis **survives** the addition of pre-2020 data: a minority of earnings gaps produce very large subsequent moves, and the average 6M opportunity distribution is nearly unchanged from V3. But V4 makes clear that the edge is not a single magic filter and not a static post-COVID phenomenon.

The most durable hierarchy is: **(1) volatility/ability to move — ADR; (2) market regime; (3) event magnitude and relative participation — gap, turnover, volume; (4) price acceptance after the open — especially 5–10M Green; (5) secondary phenotype/catalyst enrichers — deep ATH drawdown, younger age, revenue surprise / big beats / EPS state.**

The biggest lesson for the next stage is not to keep inventing filters. The selection research is mature enough. The next uncertainty is execution: **when can you enter without chasing, where can you place a survivable stop, how often do the eventual monsters stop out first, and which exit method captures the large MFE without giving back most of it?** V4’s MFE-versus-close gap proves that this is now the highest-value question.

**Do not optimize the next backtest to win rate.** This setup’s economic value is likely concentrated in a fat right tail. Report expectancy, average/median R, payoff ratio, outlier contribution, maximum drawdown, and results by reaction era/year—not just percent profitable.
