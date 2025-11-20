import os
from flask import Flask, request
import requests

app = Flask(__name__)
TOKEN = os.getenv("BOT_TOKEN")

COMMANDS = {
    "ca": "📜 合約地址：C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "web": "🌐 官方網站：https://10kcoin.com/",
    "announcements": "📣社群公告：https://t.me/tenkdogcrypto",
    "rules": "📑社群規範：https://t.me/tenkdogcrypto/71",
    "x": "𝕏 推特：https://x.com/10000timesto1",
    "dc": "💬 Discord：https://discord.com/invite/10kdog",
    "threads": "@ threads：https://www.threads.com/@_10kdog_?igshid=NTc4MTIwNjQ2YQ==",
    "invitation_code": "🔗註冊連結：https://t.me/tenthousandcommunity/10405/21167",
    "jup_lock": "🔐鎖倉資訊：https://lock.jup.ag/token/C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "pumpswap": "⛏️流動性礦池教學：https://t.me/tenkdogcrypto/72"
}

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        if 'message' in update and 'text' in update['message']:
            message_text = update['message']['text']
            chat_id = update['message']['chat']['id']
            
            if message_text.startswith('/'):
                command = message_text[1:].lower().split(' ')[0]
                
                if command in COMMANDS:
                    send_message(chat_id, COMMANDS[command])
                else:
                    help_text = "🤖 10K DOG 測試機器人\n\n可用命令：\n"
                    help_text += "\n".join([f"/{cmd}" for cmd in COMMANDS.keys()])
                    send_message(chat_id, help_text)
            
        return 'OK'
    except Exception as e:
        print(f"錯誤：{e}")
        return 'OK'

@app.route('/')
def home():
    return "🤖 10K DOG Test Bot is Running!"

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    webhook_url = f"https://{request.host}/webhook"
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
    response = requests.get(url)
    return response.json()

def send_message(chat_id, text):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    payload = {'chat_id': chat_id, 'text': text}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"發送訊息錯誤：{e}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)