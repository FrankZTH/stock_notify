import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, Union, Tuple
 
def get_ma_position_data(stock: Union[str, int], period: str = "30y") -> Dict[str, Union[str, float]]:
    """
    計算並回傳指定股票的現價及主要移動平均線（MA）數值，並四捨五入到小數點後第二位。
    使用 .tail(1).item() 獲取最新數值，提高程式碼穩定性。
    """
    stock_code = str(stock)
    ticker = stock_code if stock_code.endswith(".TW") else stock_code + ".TW"
    
    ma_periods = [5, 10, 20, 60, 120, 240]
    default_nan_result = {"股票代號": stock_code, "現價": np.nan, **{f"MA{n}": np.nan for n in ma_periods}}

    try:
        df = yf.download(ticker, period=period, auto_adjust=True, progress=False)

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

# 範例使用
if __name__ == "__main__":
    data_2330 = get_ma_position_data("2330", period="30y")

    status_bullish = get_ma_alignment_from_data(data_2330, consolidation_threshold=0.02)
    print(status_bullish)
    print("\n--- 台積電 (2330) 均線數據 (最終穩定版本 - 使用 .item()) ---")
    print(data_2330)