# Backtest lưới buy stop / sell stop XAUUSD (M1)

Luật: tâm x, d = 20 pip = 2 $, n = 3 → buy stop x+d, x+2d; sell stop x−d, x−2d; không TP;
giá chạm x±3d thì đóng hết, đan lưới mới tại đó. 0,01 lot (1 oz), vốn 1.000 $.

Lý thuyết mỗi chu kỳ (đơn vị d): k=0 nấc ngược +3 (50%), k=1 −1 (30%), k=2 −6 (20%) → kỳ vọng 0 trước phí.

## Chạy

```bash
git clone --depth 1 https://github.com/parshant65-lang/Gold-XAUUSD-1m-2020-2025-Historical-Data.git data_src
pip install numba pyarrow pandas
python backtest/load_data.py data_src/XAUUSD/1m xauusd_m1.parquet
cd backtest && python report.py ../xauusd_m1.parquet
```

Dữ liệu: OANDA M1 (mid), 01/2020 → 11/2026, 2,4 triệu nến.
Giả định: spread 0,30 $ (x3 lúc rollover 21–23h UTC), swap long −0,6 $/short +0,2 $ mỗi đêm/0,01 lot (thứ 4 x3),
gap → khớp/đóng tại giá mở nến (trượt giá).

## Hạn chế quan trọng
Nến M1 không cho biết đường đi bên trong nến. `path_mode` 0/1/2 = thứ tự O-L-H-C kiểu chuẩn / đảo / ngẫu nhiên.
Năm 2025–2026 biên độ nến M1 trung vị ~1–2 $ ≈ d, nên kết quả "chưa phí" những năm này gần như do giả định quyết định
(cần dữ liệu tick). 2020–2024 (biên độ ~0,4–0,6 $) đáng tin hơn. Nội suy thẳng giữa các điểm còn tạo một chút "xu hướng giả"
có lợi cho lưới (đo trên random walk: ~+0,19 $/chu kỳ) → kết quả thật có thể còn tệ hơn.

## Kết quả chính: xem `results_n3_d2.txt`
