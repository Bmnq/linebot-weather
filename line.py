from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import re
import os
import json

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = "igBNSrbxjJkTgX4/9QEEJi0Je2Z78EPW+HWpUkIWSb8YCYteY1FZO8xifog0UvIGuubUgw6BwNp0EAo9dX35h3sSRHtpwUDu8m8yhXJgi3JsrToOBFFHxnDR3bwiOoKuIWg3y9SEI/ttZ8tAI8vAfQdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "cfa032227546a79ef546710a3848dc7c"
SPREADSHEET_ID = "1_ex0OSY2_a4lrOe7jT1S1c2aQ4tU7XCsZ8qmpoG1L3g"

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# Google Sheets 連線
def get_sheet():
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID).sheet1
    return sheet

# 類別判斷
def guess_category(text):
    categories = {
        "🍱 餐飲": ["早餐", "午餐", "晚餐", "飲料", "咖啡", "吃", "食", "餐", "便當", "麵", "飯"],
        "🚌 交通": ["捷運", "公車", "計程車", "油", "停車", "高鐵", "火車", "uber"],
        "🛒 購物": ["超商", "超市", "買", "購物", "衣服", "鞋", "包"],
        "🎮 娛樂": ["電影", "遊戲", "KTV", "旅遊", "玩"],
        "🏥 醫療": ["醫院", "診所", "藥", "看診"],
        "🏠 居家": ["房租", "水電", "瓦斯", "網路", "電費"],
        "💼 收入": ["薪水", "薪資", "獎金", "收入", "零用錢"],
    }
    for cat, keywords in categories.items():
        for kw in keywords:
            if kw in text:
                return cat
    return "📦 其他"

# 記帳
def add_record(user_id, text, amount, record_type):
    sheet = get_sheet()
    category = guess_category(text)
    if record_type == "收入":
        category = "💼 收入"
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    sheet.append_row([now, user_id, category, text, amount, record_type])
    return category

# 本月統計
def get_monthly_summary(user_id):
    sheet = get_sheet()
    records = sheet.get_all_records()
    now = datetime.now()
    month = now.strftime("%Y/%m")

    income = 0
    expense = 0
    categories = {}

    for r in records:
        if str(r["用戶ID"]) != str(user_id):
            continue
        if not str(r["日期"]).startswith(month):
            continue
        amt = float(r["金額"])
        if r["收支"] == "收入":
            income += amt
        else:
            expense += amt
            cat = r["類別"]
            categories[cat] = categories.get(cat, 0) + amt

    balance = income - expense
    cat_text = ""
    for cat, amt in sorted(categories.items(), key=lambda x: -x[1]):
        cat_text += f"  {cat}：${amt:.0f}\n"

    return income, expense, balance, cat_text

# 預算設定
def set_budget(user_id, amount):
    sheet = get_sheet()
    records = sheet.get_all_records()
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    # 找看看有沒有已存在的預算紀錄
    for i, r in enumerate(records):
        if str(r["用戶ID"]) == str(user_id) and r["類別"] == "⚙️ 預算":
            sheet.update_cell(i + 2, 5, amount)
            return
    sheet.append_row([now, user_id, "⚙️ 預算", "每月預算", amount, "設定"])

def get_budget(user_id):
    sheet = get_sheet()
    records = sheet.get_all_records()
    for r in reversed(records):
        if str(r["用戶ID"]) == str(user_id) and r["類別"] == "⚙️ 預算":
            return float(r["金額"])
    return None

# 訊息處理
def handle_text(user_id, msg):
    msg = msg.strip()

    # 記帳：「早餐 -50」或「薪水 +30000」
    match = re.match(r"^(.+?)\s*([\+\-]?\d+)$", msg)
    if match:
        text = match.group(1).strip()
        amount = float(match.group(2))
        if amount > 0:
            record_type = "收入"
        else:
            record_type = "支出"
            amount = abs(amount)
        category = add_record(user_id, text, amount, record_type)
        emoji = "💰" if record_type == "收入" else "💸"
        return (
            f"🐷 記帳成功！\n"
            f"━━━━━━━━━━━━\n"
            f"{emoji} {record_type}：${amount:.0f}\n"
            f"📝 說明：{text}\n"
            f"🏷 類別：{category}"
        )

    # 月報表
    if "月報表" in msg or "本月" in msg or "報表" in msg:
        income, expense, balance, cat_text = get_monthly_summary(user_id)
        return (
            f"🐷 本月報表\n"
            f"━━━━━━━━━━━━\n"
            f"💰 總收入：${income:.0f}\n"
            f"💸 總支出：${expense:.0f}\n"
            f"💵 結餘：${balance:.0f}\n"
            f"━━━━━━━━━━━━\n"
            f"📊 支出分類：\n{cat_text}"
        )

    # 設定預算
    budget_match = re.match(r"設定預算\s*(\d+)", msg)
    if budget_match:
        amount = float(budget_match.group(1))
        set_budget(user_id, amount)
        return f"🐷 預算設定成功！\n本月預算：${amount:.0f}"

    # 查剩餘預算
    if "預算" in msg or "剩餘" in msg:
        budget = get_budget(user_id)
        if not budget:
            return "🐷 還沒設定預算喔！\n請傳「設定預算 15000」"
        _, expense, _, _ = get_monthly_summary(user_id)
        remaining = budget - expense
        percent = (expense / budget) * 100
        warning = ""
        if percent >= 90:
            warning = "\n🚨 預算快用完了！"
        elif percent >= 70:
            warning = "\n⚠️ 已使用超過 70%"
        return (
            f"🐷 預算狀況\n"
            f"━━━━━━━━━━━━\n"
            f"📋 本月預算：${budget:.0f}\n"
            f"💸 已花費：${expense:.0f}（{percent:.0f}%）\n"
            f"💵 剩餘：${remaining:.0f}{warning}"
        )

    # 說明
    return (
        "🐷 記帳豬使用說明\n"
        "━━━━━━━━━━━━\n"
        "📝 記帳：\n"
        "  早餐 -50（支出）\n"
        "  薪水 +30000（收入）\n\n"
        "📊 查詢：\n"
        "  本月報表\n"
        "  剩餘預算\n\n"
        "⚙️ 設定：\n"
        "  設定預算 15000"
    )

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    msg = event.message.text
    reply = handle_text(user_id, msg)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

if __name__ == "__main__":
    app.run(port=5000)