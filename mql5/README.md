# GridHedgeEA (MQL5)

Cùng luật với `backtest/`: buy stop x+d…x+(n−1)d, sell stop x−d…x−(n−1)d, không TP,
giá mid chạm x±n·d thì đóng hết và đan lưới mới. Mỗi lệnh có SL cứng ở biên đối diện + đệm.

## Cài & chạy Strategy Tester
1. MT5 → File → Open Data Folder → copy `GridHedgeEA.mq5` vào `MQL5\Experts\`.
2. Mở MetaEditor (F4) → mở file → Compile (F7). Phải ra 0 error.
3. Ctrl+R mở Strategy Tester:
   - Expert: GridHedgeEA, Symbol: XAUUSD (đúng tên mã của sàn, vd XAUUSDm, GOLD…)
   - **Modelling: "Every tick based on real ticks"** (bắt buộc — các chế độ khác là tick giả)
   - Deposit 1000 USD, leverage theo tài khoản của bạn
   - Khoảng thời gian: chọn giai đoạn sàn có tick history (thường 1–3 năm gần nhất)
   - Inputs: d = 20 pip, PipSize = 0.1 (kiểm tra: nếu giá vàng có 2 chữ số thập phân thì 0.1 giá = 10 point)
4. Kết quả: tab Backtest/Graph. File chi tiết từng chu kỳ:
   `%APPDATA%\MetaQuotes\Terminal\Common\Files\GridHedgeEA_cycles.csv`
   (cột: start, end, dir, k, orders, net, commission, swap, spread_at_close).
   Tab Journal in phân bố k ở cuối (lý thuyết n=3: k0 50%, k1 30%, k2 20%).

## Lưu ý
- Tài khoản phải là **hedging** (không phải netting), nếu không buy và sell sẽ triệt tiêu nhau.
- Kiểm tra đúng tên mã, contract size (0.01 lot = 1 oz?) và stops level của sàn.
- Khởi động lại EA sẽ đóng hết lệnh cũ của nó (theo magic number) và bắt đầu chu kỳ mới.
