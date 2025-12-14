import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Union, Tuple, Any
 
def get_ma_position_data(stock: Union[str, int], period: str = "30y") -> Dict[str, Union[str, float]]:
    """
    計算並回傳指定股票的現價及主要移動平均線（MA）數值，並四捨五入到小數點後第二位。
    使用 .tail(1).item() 獲取最新數值，提高程式碼穩定性。
    """
    stock_code = str(stock)
    # 這裡我們不再只補齊 .TW，而是準備兩個嘗試的 ticker
    ticker_tw = stock_code + ".TW"
    ticker_two = stock_code + ".TWO"
    ticker_list = [ticker_tw, ticker_two]
    
    ma_periods = [5, 10, 20, 60, 120, 240]
    default_nan_result = {"股票代號": stock_code, "現價": np.nan, **{f"MA{n}": np.nan for n in ma_periods}}
    df = pd.DataFrame()
    final_ticker = ""
    try:
        for ticker in ticker_list:
            try:
                # 嘗試下載
                df = yf.download(ticker, period=period, auto_adjust=True, progress=False, timeout=10)
                
                if not df.empty:
                    final_ticker = ticker
                    break # 成功下載後跳出迴圈
                
            except Exception as e:
                # 忽略下載失敗的錯誤，繼續嘗試下一個 ticker
                pass

        if df.empty:
            print(f"⚠️ 股票 {stock_code} ({ticker}) 數據下載失敗或為空。")
            return default_nan_result

        price_col = "Close"
        
        # 1. 取得最新收盤價 (現價)
        # 使用 .tail(1) 獲取最後一個數據點，並使用 .item() 安全地提取單一數值
        
        # 首先確保 price_col 存在且不為空
        latest_row = df[price_col].dropna().tail(1)
        
        latest_price = float(df[price_col].dropna().iloc[-1])
                


        # 2. 計算並取得均線數值
        ma_data = {}
        for n in ma_periods:
            df[f"MA{n}"] = df[price_col].rolling(n).mean()
            
            # 獲取 MA 數值
            ma_row = df[f"MA{n}"].dropna().tail(1)
            
            if ma_row.empty:
                 ma_value = np.nan
            else:
                 ma_value_raw = ma_row.item()
                 
                 # 嚴格檢查並處理 NaN
                 if pd.isna(ma_value_raw):
                     ma_value = np.nan
                 else:
                     ma_value = round(float(ma_value_raw), 2)
            
            ma_data[f"MA{n}"] = ma_value

        # 3. 組織回傳字典
        result: Dict[str, Union[str, float]] = {
            "股票代號": stock_code,
            "現價": latest_price,
            **ma_data
        }
        
        return result

    except Exception as e:
        print(f"❌ 處理股票 {stock_code} 時發生錯誤: {e}")
        return default_nan_result

def get_ma_alignment_from_data(ma_data: Dict, consolidation_threshold: float = 0.02) -> Tuple[str, Dict]:
    """
    根據已計算的 MA 數據字典，判斷股票當前的排列狀態（多頭/空頭/盤整/不明）。

    Args:
        ma_data (Dict[str, Any]): 包含現價、MA5, MA10, MA20, MA60 數值的字典。
                                  通常是 get_ma_position_data 的輸出。
        consolidation_threshold (float): 判斷盤整的 MA 間最大相對差距百分比（例如 0.02 代表 2%）。

    Returns:
        Tuple[str, Dict]: (排列狀態, 原始均線數據字典)
    """
    
    # 提取關鍵數值
    stock_code = ma_data.get("股票代號", "N/A")
    price = ma_data.get("現價")
    ma5 = ma_data.get("MA5")
    ma10 = ma_data.get("MA10")
    ma20 = ma_data.get("MA20")
    ma60 = ma_data.get("MA60")
    
    # 檢查數據完整性 (至少要有短期到中期均線)
    # 這裡使用 pd.isna 判斷 NaN，因為字典中的值可能是 np.nan 或 float
    if any(pd.isna(x) for x in [price, ma5, ma10, ma20, ma60]):
        return "數據不完整"

    # --- 1. 強勢多頭排列判斷 (Bullish Alignment) ---
    # 條件：均線多頭排列且現價高於 MA5
    if (ma5 > ma10 > ma20 > ma60) and (price > ma5):
        return "多頭排列"

    # --- 2. 強勢空頭排列判斷 (Bearish Alignment) ---
    # 條件：均線空頭排列且現價低於 MA5
    if (ma5 < ma10 < ma20 < ma60) and (price < ma5):
        return "空頭排列"

    # --- 3. 盤整/均線糾纏判斷 (Consolidation) ---
    # 邏輯：短期和中期均線 (MA5, MA10, MA20) 彼此數值非常接近
    ma_short_mid = [ma5, ma10, ma20]
    
    # 計算這三條均線之間的相對最大差距
    max_ma = max(ma_short_mid)
    min_ma = min(ma_short_mid)
    
    # 使用相對差距百分比來判斷是否糾結
    # MaxGap = (Max - Min) / Min
    relative_gap = (max_ma - min_ma) / min_ma
    
    if relative_gap <= consolidation_threshold:
        return f"盤整/均線糾纏 (差距 < {consolidation_threshold*100:.2f}%)"
    
    # --- 4. 趨勢不明顯 (Uncertain) ---
    return "趨勢不明顯"



def calculate_ma_scores(ma_data: Dict[str, Union[str, float]]) -> Dict[str, Any]:
    """
    根據股價與 MA240, MA60, MA20 的相對位置，計算買點分數和偏離度。
    
    Args:
        ma_data: 由 get_ma_position_data 產生的字典。
        
    Returns:
        包含分數、各均線偏離度及買點判斷的字典。
    """
    current_price = ma_data.get("現價")
    ma240 = ma_data.get("MA240")
    ma60 = ma_data.get("MA60")
    ma20 = ma_data.get("MA20")
    
    # 檢查核心數據是否完整
    if any(pd.isna(v) or v is None for v in [current_price, ma240, ma60, ma20]):
        return {"MA買點分數": 0, "D240": np.nan, "D60": np.nan, "D20": np.nan, "買點判斷": "數據缺失"}
    
    buy_score = 0
    ma_devs = {} # 儲存偏離度
    
    # 計算各均線偏離度 (D_n)，並轉為百分比
    # 必須確保分母不為零，雖然在股價數據中幾乎不可能，但量化程式碼應保持嚴謹。
    
    ma_periods = [240, 60, 20]
    for n in ma_periods:
        ma_key = f"MA{n}"
        ma_value = ma_data.get(ma_key)
        
        # 使用 0.0001 避免除以零
        Dn = ((current_price - ma_value) / (ma_value + 0.0001)) * 100
        ma_devs[f"D{n}"] = round(Dn, 2)
        
        # --- 依據 MA240, MA60, MA20 進行計分 ---
        if n == 240:
            if Dn <= 0:  # 貼近年線或略低 (最佳逆向買點)
                buy_score += 6
            elif 0 < Dn <= 5: # 剛突破年線
                buy_score += 4
        
        elif n == 60:
            if -3 <= Dn <= 0:  # 貼近季線
                buy_score += 3
            elif 0 < Dn <= 3:  # 剛突破季線
                buy_score += 1
                
        elif n == 20:
            if -1 <= Dn <= 1:  # 緊貼月線
                buy_score += 1
# --- 額外獎勵分數 ---
    D240 = ma_devs['D240']
    D60 = ma_devs['D60']
    print(buy_score)
    if D240 < 0 and D60 > 0:
        buy_score += 2 # 底部反彈 (長線低於，中線高於)
        status = "長線支撐/中期反彈"
    elif buy_score >= 8:
        status = "強勁買點"
    elif buy_score >= 5:
        status = "潛力觀察"
    else:
        status = "位置偏高/趨勢不明"
        
    return {
        "MA買點分數": buy_score, 
        "D240": ma_devs['D240'], 
        "D60": ma_devs['D60'], 
        "D20": ma_devs['D20'],
        "買點判斷": status,
    }
# 範例使用
# if __name__ == "__main__":
#     data_2330 = get_ma_position_data("2330", period="30y")

#     status_bullish = get_ma_alignment_from_data(data_2330, consolidation_threshold=0.02)
#     print(status_bullish)
#     print("\n--- 台積電 (2330) 均線數據 (最終穩定版本 - 使用 .item()) ---")
#     print(data_2330)