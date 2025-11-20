import os
from flask import Flask, request
import requests
import json
import datetime

app = Flask(__name__)
TOKEN = os.getenv("BOT_TOKEN")

# 超級管理員 ID（替換為您的 Telegram User ID）
SUPER_ADMIN = 123456789  # 請替換為您的實際 ID

# 管理員名單
ADMINS = {
    SUPER_ADMIN: True,  # 超級管理員
    # 可在私聊中使用 /admin add_admin [用戶ID] 新增其他管理員
}

# 允許的話題（群組ID_話題ID）
ALLOWED_THREADS = {
    # 格式: "群組ID_話題ID": True
    # 範例: "-100123456789_0": True   (主聊天室)
    # 範例: "-100123456789_123": True (具體話題)
}

# 操作記錄
ADMIN_LOGS = []

# 一般用戶命令
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

# 權限檢查函數
def is_admin(user_id):
    return user_id == SUPER_ADMIN or user_id in ADMINS

def is_super_admin(user_id):
    return user_id == SUPER_ADMIN

# 操作記錄函數
def log_admin_action(admin_id, action, target_id=None, details=None):
    log_entry = {
        'timestamp': datetime.datetime.now().isoformat(),
        'admin_id': admin_id,
        'action': action,
        'target_id': target_id,
        'details': details
    }
    ADMIN_LOGS.append(log_entry)
    if len(ADMIN_LOGS) > 500:
        ADMIN_LOGS.pop(0)

# 權限檢查函數
def should_process_message(update, user_id, message_text):
    chat_id = update['message']['chat']['id']
    thread_id = update['message'].get('message_thread_id')
    
    # 建立話題識別碼（主聊天室 thread_id = 0）
    thread_key = f"{chat_id}_{thread_id if thread_id else 0}"
    
    # 1. 管理員的管理指令永遠允許
    if (is_admin(user_id) and 
        message_text in ['/admin add_thread', '/admin remove_thread']):
        return True
    
    # 2. 一般指令需要話題已被允許
    return thread_key in ALLOWED_THREADS

# 設定命令清單
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
        ("start", "✅ 開啟選單"),
        ("help", "📋 指令清單")
    ]:
        commands_list.append({"command": cmd, "description": description})
    
    payload = {"commands": commands_list}
    requests.post(url, json=payload)

# 一般用戶按鈕選單
def create_reply_markup():
    keyboard = [
        [{"text": "📜 合約地址", "callback_data": "ca"}],
        [{"text": "🌐 官網網站", "callback_data": "web"},{"text": "📣 社群公告", "callback_data": "announcements"},{"text": "📑 社群規範", "callback_data": "rules"}],
        [{"text": "🔐 鎖倉資訊", "callback_data": "jup_lock"},{"text": "⛏️ 流動性礦池教學", "callback_data": "pumpswap"},{"text": "🔗 註冊連結", "callback_data": "invitation_code"}],
        [{"text": "𝕏 twitter推特", "callback_data": "x"}, {"text": "💬 Discord", "callback_data": "dc"}, {"text": "@ Threads", "callback_data": "threads"}],
        [{"text": "📋 所有可用指令", "callback_data": "help"}]
    ]
    return {"inline_keyboard": keyboard}

# 管理員私聊按鈕選單
def create_private_admin_markup(user_id):
    keyboard = [
        [{"text": "👥 管理員列表", "callback_data": "private_list_admins"}],
        [{"text": "➕ 新增管理員", "callback_data": "private_add_admin"}],
        [{"text": "❌ 移除管理員", "callback_data": "private_remove_admin"}],
        [{"text": "📋 話題列表", "callback_data": "private_list_threads"}],
        [{"text": "🛠️ 群組指令說明", "callback_data": "private_group_commands"}],
    ]
    
    if is_super_admin(user_id):
        keyboard.append([{"text": "📊 操作紀錄", "callback_data": "private_view_logs"}])
    
    keyboard.append([{"text": "🔙 主選單", "callback_data": "private_back_to_main"}])
    
    return {"inline_keyboard": keyboard}

# 群組管理指令處理
def handle_group_admin_command(message_text, chat_id, user_id, update):
    thread_id = update['message'].get('message_thread_id')
    
    # 建立話題識別碼
    thread_key = f"{chat_id}_{thread_id if thread_id else 0}"
    
    if message_text == '/admin add_thread':
        ALLOWED_THREADS[thread_key] = True
        if thread_id:
            send_message(chat_id, "✅ 已允許當前話題", None, thread_id)
        else:
            send_message(chat_id, "✅ 已允許主聊天室")
        log_admin_action(user_id, "add_thread", details=thread_key)
            
    elif message_text == '/admin remove_thread':
        if thread_key in ALLOWED_THREADS:
            del ALLOWED_THREADS[thread_key]
            if thread_id:
                send_message(chat_id, "❌ 已移除當前話題權限", None, thread_id)
            else:
                send_message(chat_id, "❌ 已移除主聊天室權限")
            log_admin_action(user_id, "remove_thread", details=thread_key)
        else:
            if thread_id:
                send_message(chat_id, "❌ 此話題未被允許", None, thread_id)
            else:
                send_message(chat_id, "❌ 主聊天室未被允許")
    
    # /admin 單獨輸入時靜默
    elif message_text == '/admin':
        pass

# 私聊管理員命令處理
def handle_private_admin_command(message_text, chat_id, user_id):
    if message_text.startswith('/admin add_admin '):
        parts = message_text.split(' ')
        if len(parts) > 2:
            try:
                new_admin_id = int(parts[2])
                ADMINS[new_admin_id] = True
                send_message(chat_id, f"✅ 已新增管理員: {new_admin_id}")
                log_admin_action(user_id, "add_admin", target_id=new_admin_id)
            except ValueError:
                send_message(chat_id, "❌ 請提供有效的用戶ID")
                
    elif message_text.startswith('/admin remove_admin '):
        parts = message_text.split(' ')
        if len(parts) > 2:
            try:
                remove_admin_id = int(parts[2])
                if remove_admin_id in ADMINS and remove_admin_id != SUPER_ADMIN:
                    del ADMINS[remove_admin_id]
                    send_message(chat_id, f"❌ 已移除管理員: {remove_admin_id}")
                    log_admin_action(user_id, "remove_admin", target_id=remove_admin_id)
                else:
                    send_message(chat_id, "❌ 該用戶不是管理員或是超級管理員")
            except ValueError:
                send_message(chat_id, "❌ 請提供有效的用戶ID")
                
    elif message_text == '/admin list_admins':
        admin_list = "\n".join([f"👤 {admin_id}" for admin_id in ADMINS.keys()])
        send_message(chat_id, f"👥 管理員列表:\n{admin_list}")
        
    elif message_text == '/admin list_threads':
        if not ALLOWED_THREADS:
            send_message(chat_id, "📋 目前沒有允許的話題")
        else:
            thread_list = "\n".join([f"✅ {thread_key}" for thread_key in ALLOWED_THREADS.keys()])
            send_message(chat_id, f"📋 允許的話題列表:\n{thread_list}")
        
    elif message_text == '/admin commands':
        commands_help = """🛠️ 群組管理指令說明：

在群組或話題中使用以下指令：

/admin add_thread
✅ 允許當前話題使用機器人功能

/admin remove_thread  
❌ 移除當前話題的機器人權限

⚠️ 注意：
- 主聊天室也被視為一個「話題」
- 輸入 /admin 單獨時不會有任何回應"""
        send_message(chat_id, commands_help)

# 超級管理員專屬命令
def handle_super_admin_commands(message_text, chat_id, user_id):
    if message_text.startswith('/admin logs'):
        parts = message_text.split(' ')
        count = int(parts[2]) if len(parts) > 2 else 10
        
        logs = ADMIN_LOGS[-count:] if count <= len(ADMIN_LOGS) else ADMIN_LOGS
        log_text = "📊 最近管理操作紀錄：\n\n"
        
        for log in reversed(logs):
            time = log['timestamp'][11:16]
            admin_info = f"👤 {log['admin_id']}"
            action_info = f"📝 {log['action']}"
            target_info = f"→ 👥 {log['target_id']}" if log['target_id'] else ""
            
            log_text += f"⏰ {time} | {admin_info}\n   {action_info} {target_info}\n\n"
        
        send_message(chat_id, log_text)

# 私聊管理員按鈕處理
def handle_private_admin_button(callback_data, chat_id, user_id):
    if callback_data == 'private_list_admins':
        admin_list = "\n".join([f"👤 {admin_id}" for admin_id in ADMINS.keys()])
        send_message(chat_id, f"👥 管理員列表:\n{admin_list}")
        
    elif callback_data == 'private_add_admin':
        send_message(chat_id, "請使用指令：/admin add_admin [用戶ID]")
        
    elif callback_data == 'private_remove_admin':
        send_message(chat_id, "請使用指令：/admin remove_admin [用戶ID]")
        
    elif callback_data == 'private_list_threads':
        if not ALLOWED_THREADS:
            send_message(chat_id, "📋 目前沒有允許的話題")
        else:
            thread_list = "\n".join([f"✅ {thread_key}" for thread_key in ALLOWED_THREADS.keys()])
            send_message(chat_id, f"📋 允許的話題列表:\n{thread_list}")
        
    elif callback_data == 'private_group_commands':
        commands_help = """🛠️ 群組管理指令說明：

在群組或話題中使用以下指令：

/admin add_thread
✅ 允許當前話題使用機器人功能

/admin remove_thread  
❌ 移除當前話題的機器人權限

⚠️ 注意：
- 主聊天室也被視為一個「話題」
- 輸入 /admin 單獨時不會有任何回應"""
        send_message(chat_id, commands_help)
        
    elif callback_data == 'private_view_logs' and is_super_admin(user_id):
        logs = ADMIN_LOGS[-10:]
        if not logs:
            send_message(chat_id, "📊 目前沒有操作紀錄")
        else:
            log_text = "📊 最近10筆操作：\n\n"
            for log in reversed(logs):
                time = log['timestamp'][11:16]
                log_text += f"⏰ {time} | 👤 {log['admin_id']} | 📝 {log['action']}"
                if log['target_id']:
                    log_text += f" → 👥 {log['target_id']}"
                log_text += "\n"
            send_message(chat_id, log_text)
        
    elif callback_data == 'private_back_to_main':
        send_message(chat_id, "🐾 歡迎使用10K DOG 官方BOT", create_reply_markup())

# 一般用戶命令處理
def handle_user_commands(message_text, chat_id, user_id, is_private):
    if message_text == '/start':
        welcome_text = "🐾 歡迎使用10K DOG 官方BOT\n請選擇下方按鈕或輸入指令獲取資訊！"
        send_message(chat_id, welcome_text, create_reply_markup())
        
    elif message_text == '/help':
        help_text = """📋 指令清單：

/start - ✅ 開啟選單
/help - 📋 顯示指令清單
/ca - 📜 合約地址
/web - 🌐 官方網站
/announcements - 📣 社群公告
/rules - 📑 社群規範
/jup_lock - 🔐 鎖倉資訊
/pumpswap - ⛏️ 流動性礦池教學
/invitation_code - 🔗 註冊連結
/x - 𝕏 Twitter推特
/dc - 💬 Discord社群
/threads - @ Threads"""
        send_message(chat_id, help_text)
        
    elif message_text.startswith('/'):
        command = message_text[1:].lower().split(' ')[0]
        if command in COMMANDS:
            send_message(chat_id, COMMANDS[command])
        else:
            pass  # 未知命令不回應

# 主 webhook 處理
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        # 處理一般訊息
        if 'message' in update and 'text' in update['message']:
            message_text = update['message']['text']
            chat_id = update['message']['chat']['id']
            user_id = update['message']['from']['id']
            is_private = not str(chat_id).startswith('-100')
            
            # 🔒 一般用戶管理指令過濾
            if message_text.startswith('/admin') and not is_admin(user_id):
                return 'OK'  # 一般用戶：完全靜默
            
            # 🚫 話題權限檢查
            if not is_private and not should_process_message(update, user_id, message_text):
                return 'OK'  # 話題權限不足，靜默
            
            # 👑 管理員命令處理
            if is_admin(user_id) and message_text.startswith('/admin'):
                if is_private:
                    if message_text == '/admin':
                        menu_text = "👑 管理員控制面板"
                        markup = create_private_admin_markup(user_id)
                        send_message(chat_id, menu_text, markup)
                    else:
                        if is_super_admin(user_id) and message_text.startswith('/admin logs'):
                            handle_super_admin_commands(message_text, chat_id, user_id)
                        else:
                            handle_private_admin_command(message_text, chat_id, user_id)
                else:
                    handle_group_admin_command(message_text, chat_id, user_id, update)
            
            # 👤 一般用戶命令處理
            else:
                handle_user_commands(message_text, chat_id, user_id, is_private)
        
        # 處理按鈕點擊
        elif 'callback_query' in update:
            callback_data = update['callback_query']['data']
            chat_id = update['callback_query']['message']['chat']['id']
            user_id = update['callback_query']['from']['id']
            is_private = not str(chat_id).startswith('-100')
            
            # 一般按鈕處理
            if callback_data in COMMANDS:
                send_message(chat_id, COMMANDS[callback_data])
            elif callback_data == 'help':
                help_text = "📋 所有可用指令：\n" + "\n".join([f"/{cmd}" for cmd in COMMANDS.keys()])
                send_message(chat_id, help_text)
            
            # 私聊管理員按鈕處理
            elif is_private and callback_data.startswith('private_'):
                handle_private_admin_button(callback_data, chat_id, user_id)
            
            # 回答回調查詢
            answer_callback_query(update['callback_query']['id'])
            
        return 'OK'
    except Exception as e:
        print(f"錯誤：{e}")
        return 'OK'

def answer_callback_query(callback_query_id):
    url = f'https://api.telegram.org/bot{TOKEN}/answerCallbackQuery'
    payload = {'callback_query_id': callback_query_id}
    requests.post(url, json=payload)

def send_message(chat_id, text, reply_markup=None, thread_id=None):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    if thread_id:
        payload['message_thread_id'] = thread_id
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
    set_bot_commands()
    return response.json()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
