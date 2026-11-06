"""Backtest lưới buy stop / sell stop trên XAUUSD M1.

Luật (n nấc, bước d):
  - Tâm x. Buy stop tại x+d … x+(n-1)d, sell stop tại x-d … x-(n-1)d, không TP.
  - Giá (mid) chạm x+nd hoặc x-nd -> đóng tất cả, đan lưới mới với tâm = giá đó.
  - Không đặt lệnh ở x±nd (lệnh đó khớp rồi đóng ngay, chỉ mất spread).

Mô hình khớp lệnh:
  - Giá dữ liệu là mid (OANDA). Mỗi lệnh tốn đúng 1 spread (mua ở ask, đóng ở bid).
  - Đường đi trong nến (path_mode): 0 = nến tăng O->L->H->C, nến giảm O->H->L->C;
    1 = đảo ngược; 2 = ngẫu nhiên. Nội suy thẳng giữa các điểm.
  - Khoảng trống giữa 2 nến (gap, nghỉ cuối tuần) được xử lý như nhảy giá:
    lệnh chờ bị vượt qua khớp tại giá mới, chạm ngưỡng đóng thì đóng tại giá mới (trượt giá).
  - Spread nhân `roll_mult` trong giờ rollover 21:00-22:59 UTC.
  - Swap tính mỗi khi vượt 21:00 UTC với vị thế đang mở (thứ 4 x3).

Đơn vị: 0.01 lot vàng = 1 oz -> lãi/lỗ (USD) = chênh lệch giá (USD) x lot_oz.
1 pip vàng = 0.1 USD, nên d = 20 pip = 2.0 USD.
"""
import argparse
import numpy as np
import pandas as pd
from numba import njit

# kiểu kết quả chu kỳ
END_UP, END_DOWN = 1, -1


@njit(cache=True)
def simulate(ts, o, h, l, c, d, n, spread, roll_mult, swap_long, swap_short,
             hour_ok, lot_oz, balance0, path_mode):
    nb = len(o)
    maxc = nb * 8 + 10
    # bản ghi chu kỳ
    cy_start = np.empty(maxc, np.int64)
    cy_end = np.empty(maxc, np.int64)
    cy_dir = np.empty(maxc, np.int8)
    cy_k = np.empty(maxc, np.int8)          # số nấc phía ngược bị khớp
    cy_gross = np.empty(maxc, np.float64)   # lãi/lỗ theo giá mid, chưa phí
    cy_cost = np.empty(maxc, np.float64)    # spread
    cy_swap = np.empty(maxc, np.float64)
    cy_orders = np.empty(maxc, np.int16)
    cy_gap = np.empty(maxc, np.bool_)
    ncy = 0

    eq_t = np.empty(nb, np.int64)
    eq_v = np.empty(nb, np.float64)

    balance = balance0
    peak = balance0
    maxdd = 0.0
    min_eq = balance0

    active = False
    x = 0.0
    U = 0      # số buy đã khớp (nấc 1..U)
    D = 0      # số sell đã khớp
    cost = 0.0
    swp = 0.0
    t0 = 0
    gapped = False
    last_price = o[0]

    pts = np.empty(5, np.float64)

    for i in range(nb):
        hr = (ts[i] // 3600000) % 24
        sp = spread * (roll_mult if (hr == 21 or hr == 22) else 1.0)

        # swap: vượt mốc 21:00 UTC giữa nến trước và nến này
        if i > 0 and active and (U + D) > 0:
            prev_day_h = ts[i - 1] // 3600000
            cur_day_h = ts[i] // 3600000
            # số mốc 21:00 bị vượt
            a = (prev_day_h - 21) // 24
            b = (cur_day_h - 21) // 24
            for m in range(a + 1, b + 1):
                hm = m * 24 + 21
                dow = ((hm // 24) + 3) % 7  # 0=thứ 2 (1970-01-01 là thứ 5)
                mult = 3.0 if dow == 2 else 1.0
                swp += mult * lot_oz * (U * swap_long + D * swap_short)

        # khởi động lưới nếu chưa có
        if not active:
            if hour_ok[hr]:
                active = True
                x = o[i]
                U = 0
                D = 0
                cost = 0.0
                swp = 0.0
                t0 = ts[i]
                gapped = False
            last_price = o[i]

        # ---- gap giữa nến trước và nến này ----
        if active and i > 0:
            p = o[i]
            if abs(p - last_price) > 1e-9 and (ts[i] - ts[i - 1]) > 60000:
                # nhảy giá: khớp các lệnh bị vượt tại giá p
                while U < n - 1 and p >= x + (U + 1) * d:
                    U += 1
                    cost += sp
                    gapped = True
                while D < n - 1 and p <= x - (D + 1) * d:
                    D += 1
                    cost += sp
                    gapped = True
                if p >= x + n * d or p <= x - n * d:
                    # đóng tại p (trượt giá)
                    g = 0.0
                    for k in range(1, U + 1):
                        g += p - (x + k * d)
                    for k in range(1, D + 1):
                        g += (x - k * d) - p
                    if ncy < maxc:
                        cy_start[ncy] = t0
                        cy_end[ncy] = ts[i]
                        cy_dir[ncy] = END_UP if p > x else END_DOWN
                        cy_k[ncy] = D if p > x else U
                        cy_gross[ncy] = g * lot_oz
                        cy_cost[ncy] = cost * lot_oz
                        cy_swap[ncy] = swp
                        cy_orders[ncy] = U + D
                        cy_gap[ncy] = True
                        ncy += 1
                    balance += (g - cost) * lot_oz + swp
                    if hour_ok[hr]:
                        x = p
                        U = 0
                        D = 0
                        cost = 0.0
                        swp = 0.0
                        t0 = ts[i]
                        gapped = False
                    else:
                        active = False
                last_price = p

        # ---- đường đi trong nến ----
        # điểm đầu = close nến trước (nếu liền kề, đi liên tục tới open)
        pts[0] = last_price
        pts[1] = o[i]
        bull = c[i] >= o[i]
        if path_mode == 1:
            bull = not bull
        elif path_mode == 2:
            bull = np.random.random() < 0.5
        if bull:
            pts[2] = l[i]; pts[3] = h[i]; pts[4] = c[i]
        else:
            pts[2] = h[i]; pts[3] = l[i]; pts[4] = c[i]

        for s in range(4):
            a_ = pts[s]
            b_ = pts[s + 1]
            cur = a_
            while active:
                if b_ > cur:
                    # đi lên: mốc kế tiếp phía trên
                    nxt_lvl = U + 1
                    nxt = x + nxt_lvl * d
                    if nxt > b_ + 1e-9:
                        break
                    cur = nxt
                    if nxt_lvl < n:
                        U = nxt_lvl
                        cost += sp
                    else:
                        g = 0.0
                        for k in range(1, U + 1):
                            g += cur - (x + k * d)
                        for k in range(1, D + 1):
                            g += (x - k * d) - cur
                        if ncy < maxc:
                            cy_start[ncy] = t0
                            cy_end[ncy] = ts[i]
                            cy_dir[ncy] = END_UP
                            cy_k[ncy] = D
                            cy_gross[ncy] = g * lot_oz
                            cy_cost[ncy] = cost * lot_oz
                            cy_swap[ncy] = swp
                            cy_orders[ncy] = U + D
                            cy_gap[ncy] = gapped
                            ncy += 1
                        balance += (g - cost) * lot_oz + swp
                        if hour_ok[hr]:
                            x = cur
                            U = 0
                            D = 0
                            cost = 0.0
                            swp = 0.0
                            t0 = ts[i]
                            gapped = False
                        else:
                            active = False
                elif b_ < cur:
                    nxt_lvl = D + 1
                    nxt = x - nxt_lvl * d
                    if nxt < b_ - 1e-9:
                        break
                    cur = nxt
                    if nxt_lvl < n:
                        D = nxt_lvl
                        cost += sp
                    else:
                        g = 0.0
                        for k in range(1, U + 1):
                            g += cur - (x + k * d)
                        for k in range(1, D + 1):
                            g += (x - k * d) - cur
                        if ncy < maxc:
                            cy_start[ncy] = t0
                            cy_end[ncy] = ts[i]
                            cy_dir[ncy] = END_DOWN
                            cy_k[ncy] = U
                            cy_gross[ncy] = g * lot_oz
                            cy_cost[ncy] = cost * lot_oz
                            cy_swap[ncy] = swp
                            cy_orders[ncy] = U + D
                            cy_gap[ncy] = gapped
                            ncy += 1
                        balance += (g - cost) * lot_oz + swp
                        if hour_ok[hr]:
                            x = cur
                            U = 0
                            D = 0
                            cost = 0.0
                            swp = 0.0
                            t0 = ts[i]
                            gapped = False
                        else:
                            active = False
                else:
                    break

            # equity thả nổi tại điểm b_ (đáy/đỉnh/close của nến)
            fl = 0.0
            if active:
                for k in range(1, U + 1):
                    fl += b_ - (x + k * d)
                for k in range(1, D + 1):
                    fl += (x - k * d) - b_
                fl = (fl - cost) * lot_oz + swp
            eq = balance + fl
            if eq < min_eq:
                min_eq = eq
            if eq > peak:
                peak = eq
            if peak - eq > maxdd:
                maxdd = peak - eq
        last_price = c[i]
        eq_t[i] = ts[i]
        eq_v[i] = eq

    return (cy_start[:ncy], cy_end[:ncy], cy_dir[:ncy], cy_k[:ncy], cy_gross[:ncy],
            cy_cost[:ncy], cy_swap[:ncy], cy_orders[:ncy], cy_gap[:ncy],
            eq_t, eq_v, balance, maxdd, min_eq)


def run(df, d=2.0, n=3, spread=0.30, roll_mult=3.0, swap_long=-0.60, swap_short=0.20,
        hours=None, lot_oz=1.0, balance0=1000.0, path_mode=0):
    hour_ok = np.zeros(24, np.bool_)
    hour_ok[list(range(24)) if hours is None else list(hours)] = True
    r = simulate(df.timestamp.values.astype(np.int64), df.open.values, df.high.values,
                 df.low.values, df.close.values, d, n, spread, roll_mult,
                 swap_long, swap_short, hour_ok, lot_oz, balance0, path_mode)
    cy = pd.DataFrame(dict(start=pd.to_datetime(r[0], unit="ms"), end=pd.to_datetime(r[1], unit="ms"),
                           dir=r[2], k=r[3], gross=r[4], cost=r[5], swap=r[6], orders=r[7], gap=r[8]))
    cy["net"] = cy.gross - cy.cost + cy.swap
    eq = pd.Series(r[10], index=pd.to_datetime(r[9], unit="ms"))
    return cy, eq, dict(final=r[11], maxdd=r[12], min_eq=r[13])


def summary(cy, eq, st, label=""):
    print(f"\n=== {label} ===")
    print(f"Số chu kỳ: {len(cy):,}   lệnh/chu kỳ: {cy.orders.mean():.2f}")
    print(f"Lãi/lỗ theo giá (chưa phí): {cy.gross.sum():+,.0f} $")
    print(f"Spread:                    {-cy.cost.sum():+,.0f} $")
    print(f"Swap:                      {cy.swap.sum():+,.0f} $")
    print(f"RÒNG:                      {cy.net.sum():+,.0f} $   (vốn 1.000 -> {st['final']:,.0f})")
    print(f"Equity thấp nhất: {st['min_eq']:,.0f} $   Sụt giảm tối đa: {st['maxdd']:,.0f} $")
    dist = cy.groupby("k").agg(n=("net", "size"), gross=("gross", "mean"), net=("net", "mean"))
    dist["tỷ lệ"] = dist.n / len(cy)
    print(dist.to_string(float_format=lambda v: f"{v:.3f}"))
    print(f"Chu kỳ dính gap: {cy.gap.sum():,}  (lỗ ròng tệ nhất 1 chu kỳ: {cy.net.min():.2f} $)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("data")
    ap.add_argument("--d", type=float, default=2.0)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--spread", type=float, default=0.30)
    a = ap.parse_args()
    df = pd.read_parquet(a.data)
    cy, eq, st = run(df, d=a.d, n=a.n, spread=a.spread)
    summary(cy, eq, st, f"d={a.d} n={a.n} spread={a.spread}")
