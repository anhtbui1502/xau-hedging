"""Tải tick XAUUSD (bid/ask) công khai của Exness, lưu mỗi tháng 1 file .npz.

    python backtest/fetch_exness_ticks.py OUT_DIR 2023-01 2026-10
"""
import io, sys, time, zipfile, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

URL = "https://ticks.ex2archive.com/ticks/{sym}/{y}/{m:02d}/Exness_{sym}_{y}_{m:02d}.zip"


def months(a, b):
    y, m = map(int, a.split("-")); yb, mb = map(int, b.split("-"))
    while (y, m) <= (yb, mb):
        yield y, m
        m += 1
        if m == 13: y, m = y + 1, 1


def main(out, start, end, sym="XAUUSD"):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    for y, m in months(start, end):
        f = out / f"{sym}_{y}_{m:02d}.npz"
        if f.exists():
            continue
        url = URL.format(sym=sym, y=y, m=m)
        try:
            raw = urllib.request.urlopen(url, timeout=300).read()
        except Exception as e:
            print(f"{y}-{m:02d}: lỗi {e}"); continue
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            with z.open(z.namelist()[0]) as fh:
                df = pd.read_csv(fh, usecols=["Timestamp", "Bid", "Ask"])
        ts = pd.to_datetime(df.Timestamp, format="%Y-%m-%d %H:%M:%S.%fZ").astype("datetime64[ms]").astype("int64")
        np.savez(f, ts=ts.values, bid=df.Bid.values, ask=df.Ask.values)
        sp = (df.Ask - df.Bid)
        print(f"{y}-{m:02d}: {len(df):,} tick, spread trung vị {sp.median():.3f}  p95 {sp.quantile(.95):.3f}", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
