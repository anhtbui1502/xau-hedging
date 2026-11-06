"""Backtest lưới trên tick thật (bid/ask) — cùng luật với mql5/GridHedgeEA.mq5.

  - Tâm x = mid lúc đan lưới.
  - Buy stop x+k*d (k=1..n-1): kích hoạt khi ask >= mức, khớp tại ask của tick đó
    (nếu giá nhảy qua mức thì tự động bị trượt giá).
  - Sell stop x-k*d: kích hoạt khi bid <= mức, khớp tại bid.
  - mid >= x+n*d hoặc mid <= x-n*d -> đóng hết: buy đóng ở bid, sell đóng ở ask.
    Đan lưới mới ngay tại mid tick đó (nếu trong giờ cho phép).
  - Swap: mỗi lần vượt 21:00 UTC với vị thế đang mở (thứ 4 x3).
  - commission: USD mỗi lệnh (khứ hồi) cho 0.01 lot.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from numba import njit


@njit(cache=True)
def sim(ts, bid, ask, d, n, lot_oz, swap_long, swap_short, commission, hour_ok, bal0):
    N = len(ts)
    maxc = N // 20 + 10   # 1 chu kỳ cần giá đi >= 3d, luôn qua nhiều tick
    c_start = np.empty(maxc, np.int64); c_end = np.empty(maxc, np.int64)
    c_dir = np.empty(maxc, np.int8); c_k = np.empty(maxc, np.int8)
    c_net = np.empty(maxc, np.float64); c_spread = np.empty(maxc, np.float64)
    c_swap = np.empty(maxc, np.float64); c_orders = np.empty(maxc, np.int8)
    nc = 0
    buy_px = np.zeros(16); sell_px = np.zeros(16)
    active = False
    x = 0.0; U = 0; D = 0; spc = 0.0; swp = 0.0; t0 = 0
    bal = bal0; peak = bal0; maxdd = 0.0; mineq = bal0
    day_eq_t = np.empty(N // 1000 + 10, np.int64); day_eq_v = np.empty(N // 1000 + 10, np.float64); ne = 0
    for i in range(N):
        b = bid[i]; a = ask[i]; m = 0.5 * (a + b)
        hr = (ts[i] // 3600000) % 24
        # swap tại 21:00 UTC
        if active and i > 0 and (U + D) > 0:
            pa = (ts[i - 1] // 3600000 - 21) // 24
            pb = (ts[i] // 3600000 - 21) // 24
            for q in range(pa + 1, pb + 1):
                dow = ((q * 24 + 21) // 24 + 3) % 7   # 0 = thứ 2
                mult = 3.0 if dow == 2 else 1.0
                swp += mult * lot_oz * (U * swap_long + D * swap_short)
        if not active:
            if hour_ok[hr]:
                active = True; x = m; U = 0; D = 0; spc = 0.0; swp = 0.0; t0 = ts[i]
            else:
                continue
        # khớp lệnh chờ
        while U < n - 1 and a >= x + (U + 1) * d:
            buy_px[U] = a; spc += (a - b); U += 1
        while D < n - 1 and b <= x - (D + 1) * d:
            sell_px[D] = b; spc += (a - b); D += 1
        # thả nổi
        fl = 0.0
        for k in range(U):
            fl += b - buy_px[k]
        for k in range(D):
            fl += sell_px[k] - a
        fl = fl * lot_oz + swp - commission * (U + D)
        eq = bal + fl
        if eq < mineq: mineq = eq
        if eq > peak: peak = eq
        if peak - eq > maxdd: maxdd = peak - eq
        if i % 1000 == 0:
            day_eq_t[ne] = ts[i]; day_eq_v[ne] = eq; ne += 1
        # đóng chu kỳ
        up = m >= x + n * d
        dn = m <= x - n * d
        if up or dn:
            bal = eq
            c_start[nc] = t0; c_end[nc] = ts[i]; c_dir[nc] = 1 if up else -1
            c_k[nc] = D if up else U; c_net[nc] = fl; c_spread[nc] = spc * lot_oz
            c_swap[nc] = swp; c_orders[nc] = U + D; nc += 1
            if hour_ok[hr]:
                x = m; U = 0; D = 0; spc = 0.0; swp = 0.0; t0 = ts[i]
            else:
                active = False
    return (c_start[:nc], c_end[:nc], c_dir[:nc], c_k[:nc], c_net[:nc], c_spread[:nc], c_swap[:nc],
            c_orders[:nc], day_eq_t[:ne], day_eq_v[:ne], bal, maxdd, mineq)


def load(tick_dir, start=None, end=None):
    fs = sorted(Path(tick_dir).glob("*.npz"))
    parts = []
    for f in fs:
        ym = f.stem[-7:].replace("_", "-")
        if (start and ym < start) or (end and ym > end):
            continue
        z = np.load(f)
        parts.append((z["ts"], z["bid"], z["ask"]))
    ts = np.concatenate([p[0] for p in parts]); bid = np.concatenate([p[1] for p in parts])
    ask = np.concatenate([p[2] for p in parts])
    return ts, bid, ask   # các tháng đã theo thứ tự thời gian


def run(ts, bid, ask, d=2.0, n=3, lot_oz=1.0, swap_long=-0.6, swap_short=0.2, commission=0.0,
        hours=None, bal0=1000.0):
    hour_ok = np.zeros(24, np.bool_)
    hour_ok[list(range(24)) if hours is None else list(hours)] = True
    r = sim(ts, bid, ask, d, n, lot_oz, swap_long, swap_short, commission, hour_ok, bal0)
    cy = pd.DataFrame(dict(start=pd.to_datetime(r[0], unit="ms"), end=pd.to_datetime(r[1], unit="ms"),
                           dir=r[2], k=r[3], net=r[4], spread=r[5], swap=r[6], orders=r[7]))
    cy["gross"] = cy.net + cy.spread - cy.swap + commission * cy.orders
    eq = pd.Series(r[9], index=pd.to_datetime(r[8], unit="ms"))
    return cy, eq, dict(final=r[10], maxdd=r[11], min_eq=r[12])


if __name__ == "__main__":
    ts, bid, ask = load(sys.argv[1])
    print(f"{len(ts):,} tick")
    for label, hrs in [("Cả ngày", None), ("London+NY 07-16 UTC", range(7, 17))]:
        cy, eq, st = run(ts, bid, ask, hours=hrs)
        t = cy.groupby(cy.start.dt.year).agg(chu_ky=("net", "size"), gross=("gross", "sum"),
                                              spread=("spread", "sum"), swap=("swap", "sum"), net=("net", "sum"))
        t["spread"] *= -1
        t.loc["Tổng"] = t.sum()
        print(f"\n=== {label}  d=2$ n=3 0.01 lot ===")
        print(t.round(0).astype(int).to_string())
        print("tỷ lệ k:", cy.k.value_counts(normalize=True).sort_index().round(3).to_dict(),
              f"  gross/chu kỳ {cy.gross.mean():+.3f}  spread/chu kỳ {cy.spread.mean():.3f}  ròng/chu kỳ {cy.net.mean():+.3f}")
        print(f"equity thấp nhất {st['min_eq']:,.0f}  sụt giảm tối đa {st['maxdd']:,.0f}  lỗ 1 chu kỳ tệ nhất {cy.net.min():.2f}")
        bal = 1000 + cy.net.cumsum()
        hit = cy.end[bal <= 0]
        print("cháy 1.000$ sau:", (hit.iloc[0] - cy.start.iloc[0]).days if len(hit) else "không cháy", "ngày")
