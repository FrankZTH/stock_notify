import os
import pandas as pd
from io import BytesIO
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import logging
from get_stock_position import get_ma_position_data, get_ma_alignment_from_data, calculate_ma_scores
from dotenv import load_dotenv
import os
import time
from fastapi import FastAPI
import uvicorn
import os
from threading import Thread
import datetime
app_fastapi = FastAPI()

@app_fastapi.get("/")
async def root():
    return {"message": "股票機器人活著喔！", "status": "running"}

async def run_web():
    """啟動 Uvicorn 伺服器，並使用 Server 類而非 run 函式以避免阻塞"""
    port = int(os.environ.get("PORT", 10000))
    config = uvicorn.Config(app_fastapi, host="0.0.0.0", port=port, log_level="error")
    server = uvicorn.Server(config)
    
    # 使用 await 運行伺服器，它會持續運行並監聽 Port
    print(f"FastAPI Web Service 正在監聽 Port: {port}")
    await server.serve()


load_dotenv()

# ================== 設定區（全部用環境變數，Render 上超安全）==================
API_ID = int(os.getenv("API_ID"))           # Render 後台填
API_HASH = os.getenv("API_HASH")            # Render 後台填
BOT_TOKEN = os.getenv("BOT_TOKEN")          # Render 後台填
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID"))    # 你的 Telegram ID，例如 1350443089
PETER_CHAT_ID = int(os.getenv("PETER_CHAT_ID"))    # 你的 Telegram ID，例如 1350443089
PORT = int(os.getenv("PORT")) 

# 全域儲存最新的 DataFrame
latest_df: pd.DataFrame | None = None

# 建立 Pyrogram 客戶端
app = Client(
    "my_stock_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    port=PORT
)


# ==================== 加上這段：文字指令觸發更新 ====================
@app.on_message(filters.private & filters.text)
async def manual_trigger(client: Client, message: Message):
    """只要你傳「update」就立刻執行一次 daily_job"""
    if message.text.strip().lower() in ["update", "更新", "跑一次", "執行"]:
        await message.reply("收到指令，正在執行每日通知...")
        await daily_job()
        # 如果你有「前一天」版本，也可以加另一個指令
        # elif message.text.strip().lower() == "prev":
        #     await daily_job(is_previous_day=True, triggered_by_user=True, chat_id=message.chat.id)
# ================== 收到 Excel 時自動更新 ==================
@app.on_message(filters.private & filters.document)
async def receive_excel(client: Client, message: Message):
    global latest_df
    if message.document.file_name and message.document.file_name.lower().endswith(('.xlsx', '.xls')):
        await message.reply("收到 Excel，正在讀取...")
        file = await message.download(in_memory=True)
        try:
            latest_df = pd.read_excel(BytesIO(file.getbuffer()))
            rows = len(latest_df)
            cols = len(latest_df.columns)
            await message.reply(f"Excel 更新成功！\n共 {rows} 筆資料，{cols} 個欄位")
            logging.info(f"Excel 已更新，{rows} 行")
        except Exception as e:
            await message.reply(f"讀取失敗：{str(e)}")
            logging.error(f"讀 Excel 失敗: {e}")

# ----------------------------------------------------
# 2. 新增訊息處理函式：處理用戶輸入的股票代號/名稱
# ----------------------------------------------------
@app.on_message(filters.private & filters.text & ~filters.command) # 接收私聊中的文字訊息，排除指令
async def handle_stock_query(client: Client, message: Message):
    global latest_df
    query = message.text.strip().upper() # 轉換成大寫方便比對

    if latest_df is None or latest_df.empty:
        await message.reply("目前 Excel 資料為空，請先上傳檔案。")
        return

    # 判斷輸入是否為純數字的股票代號（例如：2330, 2454）
    is_ticker_query = query.isdigit()
    
    # 根據股票代號或公司名稱來過濾資料
    if is_ticker_query:
        # 股票代號比對
        matched_rows = latest_df[latest_df['股票代號'].astype(str).str.strip() == query]
    else:
        # 公司名稱包含比對
        matched_rows = latest_df[latest_df['公司名稱'].astype(str).str.contains(query, case=False, na=False)]

    if matched_rows.empty:
        await message.reply(f"找不到關於「**{query}**」的資料。")
        return

    await message.reply(f"找到 {len(matched_rows)} 筆關於「**{query}**」的報告，正在整理...")

    # 將匹配到的 DataFrame 轉換成類似 daily_job 中 results 的格式
    # 由於這裡只做搜尋，我們先假設用戶輸入的股票已滿足成長率條件，
    # 但為了讓後續的 filter_and_deduplicate_results 正常運作，
    # 這裡需要**模擬** daily_job 完整的處理流程 (這部分需要您補齊缺失的函式)
    
    # *** 注意：為了使用 MA 篩選邏輯，我們必須確保所有欄位都已計算，
    # *** 這裡採用一個簡化方式，直接對 matched_rows 進行去重和資訊提取
    
    temp_results = []
    
    # 這裡需要您將 daily_job 迴圈中，獲取 MA 資訊和計算分數的邏輯複製到這裡，
    # 才能確保 r.get('MA買點分數', 0) 等鍵是存在的。
    # 由於這些函式 (get_ma_position_data, get_ma_alignment_from_data, calculate_ma_scores)
    # 不在提供的程式碼中，我們假設您會補上，這裡只寫核心邏輯。
    
    for idx, row in matched_rows.iterrows():
        try:
            ticker = str(row['股票代號']).strip()
            name = str(row['公司名稱']).strip()
            broker = str(row['券商']).strip()
            date = str(row['日期']).strip()
            growth_25 = float(row['EPS25成長率(%)'])
            growth_26 = float(row['EPS26成長率(%)'])
            growth_27 = float(row['EPS27成長率(%)'])
            target = str(row['目標價']).strip()
            abstract = str(row['報告摘要']).strip()
            
            # --- 模擬 growth_values 和 valid_count 的計算 (用於顯示) ---
            # --- 模擬 MA 資訊獲取（重要：這裡需要您確保這部分能運行） ---
            ma_data = get_ma_position_data(ticker, period="max")
            stock_status = get_ma_alignment_from_data(ma_data, consolidation_threshold=0.02)
            ma_scores = calculate_ma_scores(ma_data)

            result = {
                "代號": ticker,
                "名稱": name,
                "目標價": target,
                "26成長率": growth_26,
                "趨勢":stock_status,
                **ma_scores,
                "報告摘要":abstract,
                "日期": date,
                "券商":broker,
            }
            temp_results.append(result)
        except Exception as e:
            logging.error(f"單獨查詢 {ticker} 處理失敗: {e}")
            continue

    # 步驟 3：使用去重函式，只保留 (代號, 券商) 組合中日期最新的那一筆
    # 注意：這裡我們**不**再強制要求 MA買點分數 > 5，而是**保留所有找到的最新報告**
    # 否則，如果用戶單獨查詢，但分數不夠，他會得不到任何資訊。
    # 如果您堅持單獨查詢也必須 MA買點分數 > 5，請改用 filter_and_deduplicate_results

    final_results = filter_and_deduplicate_results(temp_results)

            
    # final_query_results = [item['data'] for item in unique_latest_results.values()]


    # 步驟 4：格式化輸出結果
    if not final_results:
        await message.reply(f"找到關於「**{query}**」的報告，但處理後沒有有效的最新資料可顯示。")
        return
        
    response_text = f"**🔍 找到關於「{query}」的最新報告：**\n\n"
    
    # 根據 MA 買點分數降序排序，分數高的先顯示
    # final_results.sort(key=lambda x: x.get('MA買點分數', 0), reverse=True)

    for r in final_results:
        stock_code = r['代號']
        stock_name = r['名稱']
        stock_link = f"https://tw.stock.yahoo.com/quote/{stock_code}.TW/technical-analysis"
        

        response_text += (f"**<code>{stock_code}</code> {stock_name}**\n"
                          f"  ├ **目標價：** {r['目標價']}\n"
                          f"  ├ **券商：** {r['券商']} (報告日期: {r['日期']})\n"
                          f"  ├ **MA 買點分數：** `{r.get('MA買點分數', 0):.0f}` (須 > 5)\n"
                          f"  ├ **K線趨勢：** {r['趨勢']}\n"
                          f"  ├ **偏離度(240/60/20)：** {r['D240']:.2f}% / {r['D60']:.2f}% / {r['D20']:.2f}%\n"
                          f"  ├ **報告摘要：** `{r['報告摘要']}`\n"
                          f"  └ **技術分析：** <a href='{stock_link}'>點此查看 K 線</a>\n\n"
                          )

    await message.reply(
        response_text,
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True
    )
    logging.info(f"已回覆用戶查詢: {query}")

def filter_and_deduplicate_results(results_list: list) -> list:
    """
    對結果列表進行去重（同股票代號+同券商只保留日期最新的一筆）
    並篩選出 MA買點分數 > 5 的結果。
    """
    # 步驟 1：篩選 MA 買點分數 > 5
    filtered_results = [r for r in results_list if r.get('MA買點分數', 0) > 5]
    
    unique_results = {}
    for r in filtered_results:
        # 使用 '代號' 和 '券商' 作為唯一的 Key
        key = (r.get('代號'), r.get('券商'))
        # 這裡需要從 Excel 讀取時，確保 '日期' 欄位有正確儲存
        # 由於您在 daily_job 裡將 Excel 的 '日期' 欄位存入 r['日期']
        current_date_str = r.get('日期', '1970/01/01 00:00:00 AM')

        # 嘗試將日期字串轉換為 datetime 物件進行比較
        try:
            # 根據您的範例日期格式 '2025/11/12 12:00:00 AM'
            # 這裡假設 r['日期'] 已經包含了正確的日期字串
            current_date = datetime.strptime(current_date_str, '%Y/%m/%d %I:%M:%S %p')
        except ValueError:
            current_date = datetime.min
            
        # 檢查這個組合是否已存在，或當前的日期是否更新
        if key not in unique_results or current_date > unique_results[key]['date_obj']:
            unique_results[key] = {
                'data': r,
                'date_obj': current_date
            }
            
    # 將處理過後，只保留最新日期的記錄的字典轉換回列表
    final_results = [item['data'] for item in unique_results.values()]
    return final_results

# ================== 每日定時發送通知 ==================
async def daily_job():
    global latest_df
    if latest_df is None or latest_df.empty:
        text = "今日通知\n目前還沒有收到 Excel 檔案，請傳給我～"
        await app.send_message(MY_CHAT_ID, text)
        await app.send_message(PETER_CHAT_ID, text)
        return

    results = []

    # 取得 Excel 全部欄位名稱（保留給你後面用）
    all_columns = latest_df.columns.tolist()
    tt = f"Excel 欄位總共 {len(all_columns)} 個：{all_columns}"
    # await app.send_message(MY_CHAT_ID, tt)
    print(f"Excel 欄位總共 {len(all_columns)} 個：{all_columns}")

    # 必要欄位檢查（只檢查最核心的，其他有缺就跳過那檔）
    if '股票代號' not in latest_df.columns or '公司名稱' not in latest_df.columns:
        await app.send_message(MY_CHAT_ID, "Excel 缺少「股票代號」或「公司名稱」欄位")
        await app.send_message(PETER_CHAT_ID, "Excel 缺少「股票代號」或「公司名稱」欄位")
        return
    
    for idx, row in latest_df.iterrows():
        ticker = str(row['股票代號']).strip()
        name   = str(row['公司名稱']).strip()
        broker   = str(row['券商']).strip()
        date = str(row['日期']).strip()
        target = str(row['目標價']).strip()
        # abstract = str(row['報告摘要']).strip()
        # await app.send_message(MY_CHAT_ID, ticker)
        # === 條件 1：26成長率 > 15% ===
        try:
            growth_26 = float(row['EPS26成長率(%)'])
            if growth_26 <= 15:
                continue
        except:
            continue  # 轉換失敗就跳過
        print(ticker)
        # # === 條件 2：EPS25成長率(%)、EPS26成長率(%)、EPS27成長率(%) 都 > 0 ===
        growth_cols = ['EPS25成長率(%)', 'EPS26成長率(%)', 'EPS27成長率(%)']
        growth_values = []
        valid_count = 0

        if idx % 5 == 0 and idx != 0: # 例如：每處理 10 檔股票，暫停 2 秒
             print("--- 暫停 3 秒，避免頻繁查價被鎖定 ---")
             time.sleep(3)

        for col in growth_cols:
            if col not in row or pd.isna(row[col]) or row[col] == '':
                continue  # 空值直接跳過，不中斷
            try:
                val = float(row[col])
                if val > 0:
                    valid_count += 1
                growth_values.append(val)
            except:
                continue

        # 至少要有 1 個 >0 才算（你說「都>0」，但若有缺值只看有資料的）
        # 如果你嚴格要求「有填的欄位全部必須 >0」，改成下面這行：
        if valid_count == 0 or valid_count < len([v for v in growth_values if not pd.isna(v)]):
            continue

        # === 兩條件都通過，開始計算 MA 位置 ===
        try:
            print(f"正在分析 {ticker} {name}...")
            ma_data = get_ma_position_data(ticker, period="max")
            stock_status = get_ma_alignment_from_data(ma_data, consolidation_threshold=0.02)
            ma_scores = calculate_ma_scores(ma_data)
            result = {
                "代號": ticker,
                "名稱": name,
                "目標價": target,
                "26成長率": growth_26,
                # "EPS成長率正向數": valid_count,
                "成長率明細": growth_values,
                "趨勢":stock_status,
                **ma_scores,  # 展開分數與偏離度資料
                "日期": date,
                "券商":broker,
            }
            results.append(result)
            print(f"加入清單：{ticker} {name}")

        except Exception as e:
            print(f"{ticker} 計算失敗: {e}")

    results.sort(key=lambda x: x.get('MA買點分數', 0), reverse=True)
    filtered_results = [r for r in results if r.get('MA買點分數', 0) > 5]

    
    final_results = filter_and_deduplicate_results(filtered_results)
    # === 產生最終通知 ===
    if not final_results:
        text = ("今日掃描完成\n"
                "沒有股票同時滿足：\n"
                "• 26成長率 > 15%\n"
                "• EPS近三年成長率(%) 有填的欄位皆 > 0%")
    else:
        text = f"找到 {len(final_results)} 位置不錯的股票！\n\n"
        for r in final_results:
            stock_code = r['代號']
            stock_link = f"https://tw.stock.yahoo.com/quote/{stock_code}.TW/technical-analysis"
            text += (f"• <code>{r['代號']}</code> {r['名稱']}\n"
                     f"  ├ 目標價：{r['目標價']}\n"
                     f"  ├ 26成長率：{r['26成長率']:.1f}%\n"
                    #  f"  ├ 連續3 年EPS正成長：{r['EPS成長率正向數']}\n"
                     f"  ├ k線趨勢：{r['趨勢']}\n"
                     f"  ├ D240/D60/D20 偏離度：{r['D240']:.2f}% / {r['D60']:.2f}% / {r['D20']:.2f}%\n\n"
                     f"  ├ K線：**<a href='{stock_link}'><code>{stock_code}</code> {r['名稱']}</a>**\n"                     
                     f"  └ 券商：{r['券商']}\n"
                    )

        text += f"更新時間：{pd.Timestamp('now').tz_localize('Asia/Taipei').strftime('%Y-%m-%d %H:%M')}"

    await app.send_message(
        MY_CHAT_ID, 
        text, 
        parse_mode=enums.ParseMode.HTML, # <--- 將字串替換為 enums.ParseMode.HTML
        disable_web_page_preview=True
    )
    await app.send_message(
        PETER_CHAT_ID, 
        text, 
        parse_mode=enums.ParseMode.HTML, # <--- 將字串替換為 enums.ParseMode.HTML
        disable_web_page_preview=True
    )
    print(f"通知已發送，共 {len(results)} 檔符合條件")

    

# ================== 主程式啟動 ==================
async def main():
    print("股票機器人啟動中...")
    await app.start()
    print("機器人上線！可以開始傳 Excel 給我了")

    # 設定定時任務（台灣時間每天中午12:00 + 晚上10:00）
    scheduler = AsyncIOScheduler(timezone="Asia/Taipei")
    scheduler.add_job(daily_job, "cron", hour=12, minute=0)
    scheduler.add_job(daily_job, "cron", hour=22, minute=0)
    scheduler.start()

    print("排程已啟動：每天 12:00 和 22:00 發送通知")
    # 保持運行
    await asyncio.gather(
        run_web(),       # 啟動 Web 服務並監聽 Port
        asyncio.Event().wait() # 讓主程序等待，保持 Pyrogram Bot 運行
    )

# if __name__ == "__main__":
    # Render 會自動執行這個
    # app.run(main())
    # Thread(target=run_web, daemon=True).start()

if __name__ == "__main__":
    # 【使用 Pyrogram 的 app.run() 來運行主程序】
    # 這是 Pyrogram Bot 的標準啟動方式
    app.run(main()) # 這行確保 main() 函數被正確執行並阻塞