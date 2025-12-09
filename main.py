import os
import pandas as pd
from io import BytesIO
from pyrogram import Client, filters
from pyrogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import logging
from get_stock_position import get_ma_position_data, get_ma_alignment_from_data

# ================== 設定區（全部用環境變數，Render 上超安全）==================
API_ID = int(os.getenv("API_ID"))           # Render 後台填
API_HASH = os.getenv("API_HASH")            # Render 後台填
BOT_TOKEN = os.getenv("BOT_TOKEN")          # Render 後台填
MY_CHAT_ID = int(os.getenv("MY_CHAT_ID"))    # 你的 Telegram ID，例如 1350443089

# 全域儲存最新的 DataFrame
latest_df: pd.DataFrame | None = None

# 建立 Pyrogram 客戶端
app = Client(
    "my_stock_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)
# ==================== 加上這段：文字指令觸發更新 ====================
@app.on_message(filters.private & filters.text & filters.user(MY_CHAT_ID))
async def manual_trigger(client: Client, message: Message):
    """只要你傳「update」就立刻執行一次 daily_job"""
    if message.text.strip().lower() in ["update", "更新", "跑一次", "執行"]:
        await message.reply("收到指令，正在執行每日通知...")
        await daily_job(is_previous_day=False, triggered_by_user=True, chat_id=message.chat.id)
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

# ================== 每日定時發送通知 ==================
async def daily_job():
    global latest_df
    if latest_df is None or latest_df.empty:
        text = "今日通知\n目前還沒有收到 Excel 檔案，請傳給我～"
        await app.send_message(MY_CHAT_ID, text)
        return

    results = []

    # 取得 Excel 全部欄位名稱（保留給你後面用）
    all_columns = latest_df.columns.tolist()
    print(f"Excel 欄位總共 {len(all_columns)} 個：{all_columns}")

    # 必要欄位檢查（只檢查最核心的，其他有缺就跳過那檔）
    if '股票代號' not in latest_df.columns or '股票名稱' not in latest_df.columns:
        await app.send_message(MY_CHAT_ID, "Excel 缺少「股票代號」或「股票名稱」欄位")
        return

    for idx, row in latest_df.iterrows():
        ticker = str(row['股票代號']).strip()
        name   = str(row['股票名稱']).strip()

        # === 條件 1：26成長率 > 15% ===
        try:
            growth_26 = float(row['26成長率'])
            if growth_26 <= 15:
                continue
        except:
            continue  # 轉換失敗就跳過

        # === 條件 2：EPS25成長率(%)、EPS26成長率(%)、EPS27成長率(%) 都 > 0 ===
        growth_cols = ['EPS25成長率(%)', 'EPS26成長率(%)', 'EPS27成長率(%)']
        growth_values = []
        valid_count = 0

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
            ma_data = get_ma_position_data(ticker, period="30y")
            stock_status = get_ma_alignment_from_data(ma_data, consolidation_threshold=0.02)
            result = {
                "代號": ticker,
                "名稱": name,
                "26成長率": growth_26,
                "EPS成長率正向數": valid_count,
                "成長率明細": growth_values,
                "完整MA資料": ma_data,
            }
            results.append(result)
            print(f"加入清單：{ticker} {name}")

        except Exception as e:
            print(f"{ticker} 計算失敗: {e}")

    # === 產生最終通知 ===
    if not results:
        text = ("今日掃描完成\n"
                "沒有股票同時滿足：\n"
                "• 26成長率 > 15%\n"
                "• EPS近三年成長率(%) 有填的欄位皆 > 0%")
    else:
        text = f"找到 {len(results)} 檔潛力股！\n\n"
        for r in results:
            text += (f"• <code>{r['代號']}</code> {r['名稱']}\n"
                     f"  ├ 26成長率：{r['26成長率']:.1f}%\n"
                     f"  ├ EPS正成長：{r['EPS成長率正向數']}/3 年\n"
                     f"  └ 目前位置：{r['均線位置']}\n\n")

        text += f"更新時間：{pd.Timestamp('now').tz_localize('Asia/Taipei').strftime('%Y-%m-%d %H:%M')}"

    await app.send_message(MY_CHAT_ID, text, parse_mode="html", disable_web_page_preview=True)
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
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Render 會自動執行這個
    app.run(main())