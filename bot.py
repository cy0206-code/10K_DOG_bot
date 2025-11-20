import os
from flask import Flask, request
import requests
import json

app = Flask(__name__)
TOKEN = os.getenv("BOT_TOKEN")

COMMANDS = {
    "ca": "C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "web": "https://10kcoin.com/",
    "announcements": "https://t.me/tenkdogcrypto",
    "rules": "https://t.me/tenkdogcrypto/71",
    "jup_lock": "https://lock.jup.ag/token/C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "pumpswap": "https://t.me/tenkdogcrypto/72",
    "invitation_code": "https://t.me/tenthousandcommunity/10405/21167",
    "x": "https://x.com/10000timesto1",
    "dc": "https://discord.com/invite/10kdog",
    "threads": "https://www.threads.com/@_10kdog_?igshid=NTc4MTIwNjQ2YQ=="    
}

# 設定命令清單（讓 Telegram 顯示自動完成）
def set_bot_commands():
    url = f"https://api.telegram.org/bot{TOKEN}/setMyCommands"
    commands_list = []
    
    for cmd, description in [
        ("ca", "📜 合約地址"),
        ("web", "🌐 官方網站"),
        ("announcements", "📣 社群公告"),
        ("rules", "📑 社群規範"),
        ("jup_lock", "🔐 鎖倉資訊"),
        ("pumpswap", "⛏️ 流動性礦池教學"),
        ("invitation_code", "🔗 註冊連結"),
        ("x", "𝕏 推特"),
        ("dc", "💬 Discord"),
        ("threads", "@ Threads"),
        ("start", "✅ 開啟選單"),  # 修正：加上逗號
        ("help", "📋 指令清單")
    ]:
        commands_list.append({"command": cmd, "description": description})
    
    payload = {"commands": commands_list}
    requests.post(url, json=payload)

# 底部按鈕選單
def create_reply_markup():
    keyboard = [
        [{"text": "📜 合約地址", "callback_data": "ca"}],
        [{"text": "🌐 官網網站", "callback_data": "web"},{"text": "📣 社群公告", "callback_data": "announcements"},{"text": "📑 社群規範", "callback_data": "rules"}],
        [{"text": "🔐 鎖倉資訊", "callback_data": "jup_lock"},{"text": "⛏️ 流動性礦池教學", "callback_data": "pumpswap"},{"text": "🔗 註冊連結", "callback_data": "invitation_code"}],
        [{"text": "𝕏 twitter推特", "callback_data": "x"}, {"text": "💬 Discord", "callback_data": "dc"}, {"text": "@ Threads", "callback_data": "threads"}],
        [{"text": "📋 所有可用指令", "callback_data": "help"}]
    ]
    return {"inline_keyboard": keyboard}

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        # 處理一般訊息
        if 'message' in update and 'text' in update['message']:
            message_text = update['message']['text']
            chat_id = update['message']['chat']['id']
            
            if message_text == '/start':
                welcome_text = "🐾 歡迎使用10K DOG 官方機器人\n請選擇下方按鈕或輸入指令獲取資訊！"
                send_message(chat_id, welcome_text, create_reply_markup())
                
            elif message_text == '/help':
                help_text = "📋 指令清單：\n" + "\n".join([f"/{cmd}" for cmd in COMMANDS.keys()])
                send_message(chat_id, help_text)
                
            elif message_text.startswith('/'):
                command = message_text[1:].lower().split(' ')[0]
                
                if command in COMMANDS:
                    send_message(chat_id, COMMANDS[command])
                else:
                    # 未知命令：直接不回應
                    pass  # 什麼都不做
            
        # 處理按鈕點擊
        elif 'callback_query' in update:
            callback_data = update['callback_query']['data']
            chat_id = update['callback_query']['message']['chat']['id']
            
            if callback_data in COMMANDS:
                send_message(chat_id, COMMANDS[callback_data])
            elif callback_data == 'help':
                help_text = "📋 所有可用命令：\n" + "\n".join([f"/{cmd}" for cmd in COMMANDS.keys()])
                send_message(chat_id, help_text)
            
            # 回答回調查詢（移除等待狀態）
            answer_callback_query(update['callback_query']['id'])
            
        return 'OK'
    except Exception as e:
        print(f"錯誤：{e}")
        return 'OK'

def answer_callback_query(callback_query_id):
    url = f'https://api.telegram.org/bot{TOKEN}/answerCallbackQuery'
    payload = {'callback_query_id': callback_query_id}
    requests.post(url, json=payload)

def send_message(chat_id, text, reply_markup=None):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    if reply_markup:
        payload['reply_markup'] = json.dumps(reply_markup)
    
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"發送訊息錯誤：{e}")

@app.route('/')
def home():
    return "🤖 10K DOG Bot is Running!"

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    webhook_url = f"https://{request.host}/webhook"
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
    response = requests.get(url)
    
    # 同時設定命令清單
    set_bot_commands()
    
    return response.json()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
