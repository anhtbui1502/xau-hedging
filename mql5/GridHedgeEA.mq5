//+------------------------------------------------------------------+
//| GridHedgeEA.mq5                                                   |
//| Lưới buy stop / sell stop, đóng hết khi giá chạm x ± n*d.          |
//|                                                                    |
//| Luật:                                                              |
//|  - Tâm x = giá mid lúc đan lưới.                                   |
//|  - Buy stop tại x+d … x+(n-1)d, sell stop tại x-d … x-(n-1)d.      |
//|  - Không TP. SL cứng từng lệnh ở biên đối diện (+ đệm) phòng EA    |
//|    mất kết nối.                                                     |
//|  - Giá mid chạm x+n*d hoặc x-n*d -> đóng tất cả, xoá lệnh chờ,     |
//|    đan lưới mới tại giá hiện tại (nếu trong giờ cho phép).         |
//|  - Mỗi chu kỳ ghi 1 dòng vào file CSV (thư mục Common\Files).      |
//+------------------------------------------------------------------+
#property copyright "xau-hedging"
#property version   "1.00"

#include <Trade\Trade.mqh>

input double InpStepPips    = 20;     // d (pip)
input double InpPipSize     = 0.1;    // 1 pip = ? giá (vàng: 0.1)
input int    InpLevels      = 3;      // n: đóng khi chạm x ± n*d
input double InpLots        = 0.01;   // khối lượng mỗi lệnh
input double InpSLBufferPip = 5;      // SL cứng = biên đối diện + đệm (pip)
input int    InpStartHour   = 0;      // giờ server bắt đầu cho phép đan lưới mới
input int    InpEndHour     = 24;     // giờ server kết thúc (không gồm)
input ulong  InpMagic       = 20261106;
input int    InpDeviation   = 50;     // trượt giá tối đa khi đóng (point)
input string InpLogFile     = "GridHedgeEA_cycles.csv";

CTrade   trade;
double   g_d;           // bước lưới (giá)
double   g_x;           // tâm
bool     g_active = false;
datetime g_start;
int      g_maxBuys, g_maxSells;
int      g_log = INVALID_HANDLE;
ulong    g_lastDeal = 0;   // deal lớn nhất đã tính (tránh đếm trùng chu kỳ trước)

// thống kê
int      g_cycles = 0;
int      g_kCount[16];
double   g_netSum = 0;

//+------------------------------------------------------------------+
double Mid() { return (SymbolInfoDouble(_Symbol, SYMBOL_BID) + SymbolInfoDouble(_Symbol, SYMBOL_ASK)) / 2.0; }

bool HourAllowed()
{
   MqlDateTime t; TimeToStruct(TimeCurrent(), t);
   if(InpStartHour <= InpEndHour) return t.hour >= InpStartHour && t.hour < InpEndHour;
   return t.hour >= InpStartHour || t.hour < InpEndHour;   // khung qua nửa đêm
}

void CountPositions(int &buys, int &sells)
{
   buys = 0; sells = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) buys++; else sells++;
   }
}

void CloseAll()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      trade.PositionClose(tk, InpDeviation);
   }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong tk = OrderGetTicket(i);
      if(tk == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol) continue;
      if((ulong)OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      trade.OrderDelete(tk);
   }
}

bool PlaceGrid()
{
   int    digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double ask    = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid    = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double minDist = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL) * _Point;
   double buf    = InpSLBufferPip * InpPipSize;

   g_x = Mid();
   double slBuy  = NormalizeDouble(g_x - InpLevels * g_d - buf, digits);
   double slSell = NormalizeDouble(g_x + InpLevels * g_d + buf, digits);

   for(int k = 1; k < InpLevels; k++)
   {
      double pb = NormalizeDouble(g_x + k * g_d, digits);
      double ps = NormalizeDouble(g_x - k * g_d, digits);
      if(pb - ask < minDist || bid - ps < minDist)
      {
         Print("Bước lưới nhỏ hơn stops level của sàn, không đặt được lệnh.");
         CloseAll();
         return false;
      }
      if(!trade.BuyStop(InpLots, pb, _Symbol, slBuy, 0, ORDER_TIME_GTC, 0, "grid"))
         Print("BuyStop lỗi: ", trade.ResultRetcodeDescription());
      if(!trade.SellStop(InpLots, ps, _Symbol, slSell, 0, ORDER_TIME_GTC, 0, "grid"))
         Print("SellStop lỗi: ", trade.ResultRetcodeDescription());
   }
   g_active   = true;
   g_start    = TimeCurrent();
   g_maxBuys  = 0;
   g_maxSells = 0;
   return true;
}

// tổng lãi/lỗ (profit + commission + swap) các deal của EA từ lúc bắt đầu chu kỳ
void CycleResult(double &net, double &commission, double &swap)
{
   net = 0; commission = 0; swap = 0;
   if(!HistorySelect(g_start - 60, TimeCurrent() + 1)) return;
   ulong maxDeal = g_lastDeal;
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong dl = HistoryDealGetTicket(i);
      if(dl == 0 || dl <= g_lastDeal) continue;
      if(dl > maxDeal) maxDeal = dl;
      if(HistoryDealGetString(dl, DEAL_SYMBOL) != _Symbol) continue;
      if((ulong)HistoryDealGetInteger(dl, DEAL_MAGIC) != InpMagic) continue;
      double p = HistoryDealGetDouble(dl, DEAL_PROFIT);
      double c = HistoryDealGetDouble(dl, DEAL_COMMISSION);
      double s = HistoryDealGetDouble(dl, DEAL_SWAP);
      net += p + c + s; commission += c; swap += s;
   }
   g_lastDeal = maxDeal;
}

void EndCycle(int dir)
{
   int k = (dir > 0) ? g_maxSells : g_maxBuys;     // số nấc phía ngược đã khớp
   double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
   CloseAll();
   double net, com, swp;
   CycleResult(net, com, swp);

   g_cycles++;
   if(k >= 0 && k < 16) g_kCount[k]++;
   g_netSum += net;
   if(g_log != INVALID_HANDLE)
      FileWrite(g_log, TimeToString(g_start, TIME_DATE | TIME_SECONDS), TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
                dir, k, g_maxBuys + g_maxSells, DoubleToString(net, 2), DoubleToString(com, 2),
                DoubleToString(swp, 2), DoubleToString(spread, 3));
   g_active = false;
}

//+------------------------------------------------------------------+
int OnInit()
{
   g_d = InpStepPips * InpPipSize;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(InpDeviation);
   trade.SetTypeFillingBySymbol(_Symbol);
   ArrayInitialize(g_kCount, 0);

   // dọn lệnh cũ của EA (khởi động lại = bắt đầu chu kỳ mới)
   CloseAll();

   g_log = FileOpen(InpLogFile, FILE_WRITE | FILE_CSV | FILE_COMMON | FILE_ANSI, ',');
   if(g_log != INVALID_HANDLE)
      FileWrite(g_log, "start", "end", "dir", "k", "orders", "net", "commission", "swap", "spread_at_close");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(g_log != INVALID_HANDLE) FileClose(g_log);
   string s = StringFormat("Chu kỳ: %d  Ròng: %.2f", g_cycles, g_netSum);
   for(int k = 0; k < InpLevels; k++)
      s += StringFormat("  k=%d: %d (%.1f%%)", k, g_kCount[k], g_cycles > 0 ? 100.0 * g_kCount[k] / g_cycles : 0);
   Print(s);
}

void OnTick()
{
   if(!g_active)
   {
      if(HourAllowed()) PlaceGrid();
      return;
   }

   int b, s;
   CountPositions(b, s);
   if(b > g_maxBuys)  g_maxBuys  = b;
   if(s > g_maxSells) g_maxSells = s;

   double m = Mid();
   if(m >= g_x + InpLevels * g_d)      EndCycle(+1);
   else if(m <= g_x - InpLevels * g_d) EndCycle(-1);
   else
   {
      // SL cứng đã đóng hết vị thế và không còn lệnh chờ -> coi như kết thúc chu kỳ
      if(b == 0 && s == 0 && (g_maxBuys + g_maxSells) > 0)
      {
         int pend = 0;
         for(int i = OrdersTotal() - 1; i >= 0; i--)
         {
            ulong tk = OrderGetTicket(i);
            if(tk != 0 && OrderGetString(ORDER_SYMBOL) == _Symbol && (ulong)OrderGetInteger(ORDER_MAGIC) == InpMagic) pend++;
         }
         if(pend == 0) EndCycle(m > g_x ? +1 : -1);
      }
      return;
   }

   if(HourAllowed()) PlaceGrid();
}

double OnTester()
{
   return g_netSum;
}
