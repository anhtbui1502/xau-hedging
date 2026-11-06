"""Gộp các file CSV M1 XAUUSD (theo ngày) thành 1 file parquet.

Nguồn: github.com/parshant65-lang/Gold-XAUUSD-1m-2020-2025-Historical-Data
(dữ liệu gốc OANDA, giá mid, giờ UTC).

    git clone --depth 1 https://github.com/parshant65-lang/Gold-XAUUSD-1m-2020-2025-Historical-Data.git data_src
    python backtest/load_data.py data_src/XAUUSD/1m xauusd_m1.parquet
"""
import sys
from pathlib import Path
import pandas as pd

src, out = Path(sys.argv[1]), sys.argv[2]
files = sorted(src.rglob("*.csv"))
df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
df = df[["timestamp", "open", "high", "low", "close"]]
df.to_parquet(out)
print(f"{len(files)} files, {len(df):,} bars, "
      f"{pd.to_datetime(df.timestamp.iloc[0], unit='ms')} -> {pd.to_datetime(df.timestamp.iloc[-1], unit='ms')}")
