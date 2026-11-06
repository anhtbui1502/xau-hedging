"""Chạy các kịch bản cho lưới n=3, d=2$ (20 pip), 0.01 lot, vốn 1.000$."""
import sys
import numpy as np
import pandas as pd
from grid_backtest import run

df = pd.read_parquet(sys.argv[1])
SESS = {"Cả ngày": None, "London+NY 07-16 UTC": range(7, 17), "Phiên Á 23-06 UTC": [23, 0, 1, 2, 3, 4, 5, 6]}


def blowup_days(cy, start_bal=1000.0):
    """Mỗi năm bắt đầu lại 1.000$: bao nhiêu ngày thì số dư <= 0 (theo số dư đã chốt)."""
    out = {}
    for y, g in cy.groupby(cy.start.dt.year):
        bal = start_bal + g.net.cumsum()
        hit = g.end[bal <= 0]
        out[y] = (hit.iloc[0] - g.start.iloc[0]).days if len(hit) else None
    return out


print("## 1. Kịch bản chính: spread 0,30$, cả ngày, theo năm (path 0 / 1 / 2)")
for pm in (0, 1, 2):
    cy, eq, st = run(df, spread=0.30, path_mode=pm)
    t = cy.groupby(cy.start.dt.year).agg(chu_ky=("net", "size"), gross=("gross", "sum"),
                                          spread=("cost", "sum"), swap=("swap", "sum"), net=("net", "sum"))
    t["spread"] *= -1
    t.loc["Tổng"] = t.sum()
    print(f"\n### path_mode={pm}   ròng/chu kỳ {cy.net.mean():+.3f}$   tỷ lệ k={cy.k.value_counts(normalize=True).sort_index().round(3).to_dict()}")
    print(t.round(0).astype(int).to_string())
    print("Số ngày tới khi cháy 1.000$ (mỗi năm làm lại):", blowup_days(cy))

print("\n## 2. Theo phiên & mức spread (path 2 = ngẫu nhiên), chỉ 2020-2024 (nến M1 còn đủ mịn so với d)")
d24 = df[pd.to_datetime(df.timestamp, unit="ms").dt.year <= 2024]
rows = []
for sname, hrs in SESS.items():
    for sp in (0.0, 0.17, 0.30, 0.50):
        r = []
        for pm in (0, 1, 2):
            cy, eq, st = run(d24, spread=sp, hours=hrs, path_mode=pm)
            r.append(cy.net.sum())
        rows.append(dict(phien=sname, spread=sp, chu_ky=len(cy), net_path0=r[0], net_path1=r[1], net_path2=r[2],
                         net_moi_chu_ky_path2=r[2] / len(cy)))
print(pd.DataFrame(rows).round(2).to_string(index=False))
