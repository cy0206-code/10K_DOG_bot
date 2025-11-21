import os
import json
from flask import Flask, request
import requests
import datetime
import pytz

app = Flask(__name__)
TOKEN = os.environ.get("BOT_TOKEN")
SUPER_ADMIN = 8126033106
# 修改資料檔案路徑到當前工作目錄
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_data.json")
TAIWAN_TZ = pytz.timezone('Asia/Taipei')

# ========== 核心資料管理 ==========
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"載入資料錯誤: {e}")
    
    # 如果檔案不存在或讀取失敗，創建預設資料
    default_data = {
        "admins": {str(SUPER_ADMIN): {"added_by": "system", "added_time": datetime.datetime.now().isoformat(), "is_super": True}},
        "allowed_threads": {},
        "admin_logs": []
    }
    save_data(default_data)
    return default_data

def save_data(data):
    try:
        # 確保目錄存在
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        # 使用原子操作寫入，避免資料損壞
        temp_file = DATA_FILE + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # 替換原檔案
        os.replace(temp_file, DATA_FILE)
        print(f"資料已儲存至: {DATA_FILE}")
    except Exception as e:
        print(f"儲存錯誤: {e}")

# 初始化資料
data = load_data()

def get_admins(): return data.get("admins", {})
def get_threads(): return data.get("allowed_threads", {})
def get_logs(): return data.get("admin_logs", [])

def update_data(key, value):
    data[key] = value
    save_data(data)

# ========== 核心功能函數 ==========
def is_admin(user_id): return str(user_id) in get_admins()
def is_super_admin(user_id): return get_admins().get(str(user_id), {}).get('is_super', False)

def add_admin(admin_id, added_by):
    admins = get_admins()
    admin_str = str(admin_id)
    if admin_str not in admins:
        admins[admin_str] = {
            "added_by": added_by,
            "added_time": datetime.datetime.now(TAIWAN_TZ).isoformat(),
            "is_super": False
        }
        update_data("admins", admins)
        return True
    return False

def remove_admin(admin_id):
    admins = get_admins()
    admin_str = str(admin_id)
    if admin_str in admins and not admins[admin_str].get('is_super', False):
        del admins[admin_str]
        update_data("admins", admins)
        return True
    return False

def toggle_thread(chat_id, thread_id, add=True):
    threads = get_threads()
    key = f"{chat_id}_{thread_id}"
    if add:
        threads[key] = True
    elif key in threads:
        del threads[key]
    else:
        return False
    update_data("allowed_threads", threads)
    return True

def log_action(admin_id, action, target=None, details=None):
    logs = get_logs()
    
    # 獲取管理員名稱
    admin_info = get_user_info(admin_id)
    admin_name = get_display_name(admin_info) if admin_info else str(admin_id)
    
    log_entry = {
        'timestamp': datetime.datetime.now(TAIWAN_TZ).isoformat(),
        'admin_id': admin_id,
        'admin_name': admin_name,
        'action': action,
        'target_id': target,
        'details': details
    }
    
    # 如果有目標ID，也獲取目標名稱
    if target:
        target_info = get_user_info(target)
        if target_info:
            log_entry['target_name'] = get_display_name(target_info)
    
    logs.append(log_entry)
    if len(logs) > 100: logs.pop(0)
    update_data("admin_logs", logs)

# ========== 權限檢查 ==========
def should_process(update, user_id, text):
    chat_id = update['message']['chat']['id']
    
    # 私聊永遠允許
    if not str(chat_id).startswith('-100'):
        return True
    
    # 管理員指令在群組中永遠允許
    if is_admin(user_id) and text in ['/admin add_thread', '/admin remove_thread']:
        return True
    
    # 一般指令需要話題權限
    thread_id = update['message'].get('message_thread_id', 0)
    return f"{chat_id}_{thread_id}" in get_threads()

# ========== 命令定義 ==========
COMMANDS = {
    "ca": "C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "web": "https://10kcoin.com/",
    "announcements": "https://t.me/tenkdogcrypto",
    "rules": "https://t.me/tenkdogcrypto/71",
    "jup_lock": "https://lock.jup.ag/token/C9HwNWaVVecVm35raAaZBXEa4sQF3hGXszhGKpy3pump",
    "pumpswap": "https://t.me/tenkdogcrypto/72",
    "invitation_code": "https://t.me/tenthousandcommunity/10405",
    "x": "https://x.com/10000timesto1",
    "dc": "https://discord.com/invite/10kdog",
    "threads": "https://www.threads.com/@_10kdog_?igshid=NTc4MTIwNjQ2YQ=="
}

HELP_TEXT = """📋 指令清單：

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

# ========== 按鈕定義 ==========
def main_menu():
    return {
        "inline_keyboard": [
            [{"text": "📜 合約地址", "callback_data": "ca"}],
            [{"text": "🌐 官網網站", "callback_data": "web"}, {"text": "📣 社群公告", "callback_data": "announcements"}],
            [{"text": "📑 社群規範", "callback_data": "rules"}, {"text": "🔐 鎖倉資訊", "callback_data": "jup_lock"}],
            [{"text": "⛏️ 流動性礦池教學", "callback_data": "pumpswap"}, {"text": "🔗 註冊連結", "callback_data": "invitation_code"}],
            [{"text": "𝕏 Twitter推特", "callback_data": "x"}, {"text": "💬 Discord", "callback_data": "dc"}],
            [{"text": "@ Threads", "callback_data": "threads"}, {"text": "📋 所有可用指令", "callback_data": "help"}]
        ]
    }

def admin_menu(user_id):
    keyboard = [
        [{"text": "👥 管理員列表", "callback_data": "admin_list"}, {"text": "🔍 查詢TG UID", "callback_data": "admin_query_uid"}],
        [{"text": "➕ 新增管理員", "callback_data": "admin_add"}, {"text": "❌ 移除管理員", "callback_data": "admin_remove"}],
        [{"text": "📋 話題列表", "callback_data": "admin_threads"}, {"text": "🛠️ 群組指令說明", "callback_data": "admin_help"}],
    ]
    if is_super_admin(user_id):
        keyboard.append([{"text": "📊 操作紀錄", "callback_data": "admin_logs"}])
    keyboard.append([{"text": "🔙 主選單", "callback_data": "main_menu"}])
    return {"inline_keyboard": keyboard}

# ========== 用戶資訊獲取 ==========
def get_user_info(user_id):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/getChat",
            json={"chat_id": user_id},
            timeout=5
        )
        if response.status_code == 200:
            return response.json().get('result', {})
    except:
        pass
    return None

def get_display_name(user_info):
    """從用戶資訊中獲取顯示名稱"""
    if not user_info:
        return "未知用戶"
    
    first_name = user_info.get('first_name', '')
    last_name = user_info.get('last_name', '')
    username = user_info.get('username', '')
    
    full_name = f"{first_name} {last_name}".strip()
    if full_name and username:
        return f"{full_name} (@{username})"
    elif full_name:
        return full_name
    elif username:
        return f"@{username}"
    else:
        return "未知用戶"

def get_chat_info(chat_id):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/getChat",
            json={"chat_id": chat_id},
            timeout=5
        )
        if response.status_code == 200:
            return response.json().get('result', {})
    except:
        pass
    return None

def get_thread_name(chat_id, thread_id):
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/getForumTopic",
            json={"chat_id": chat_id, "message_thread_id": thread_id},
            timeout=5
        )
        if response.status_code == 200:
            return response.json().get('result', {}).get('name', '未知話題')
    except:
        pass
    return '未知話題'

# ========== 列表顯示函數 ==========
def get_admin_list_with_names():
    admins = get_admins()
    if not admins:
        return "👥 目前沒有管理員"
    
    admin_list = "👥 管理員列表：\n\n"
    for admin_id, admin_info in admins.items():
        try:
            user_info = get_user_info(int(admin_id))
            display_name = get_display_name(user_info)
            role = "👑 超級管理員" if admin_info.get('is_super', False) else "👤 管理員"
            
            admin_list += f"{role} - {display_name}\n"
            admin_list += f"🔢 ID: {admin_id}\n\n"  # 移除反引號
        except:
            admin_list += f"👤 未知用戶\n🔢 ID: {admin_id}\n\n"  # 移除反引號
    
    return admin_list

def get_thread_list_with_names():
    threads = get_threads()
    if not threads:
        return "📋 目前沒有允許的話題"
    
    thread_list = "📋 允許的話題列表：\n\n"
    for thread_key in threads.keys():
        try:
            chat_id, thread_id = thread_key.split('_')
            thread_id = int(thread_id) if thread_id != '0' else 0
            
            chat_info = get_chat_info(chat_id)
            chat_title = chat_info.get('title', '未知群組') if chat_info else '未知群組'
            
            if thread_id == 0:
                thread_list += f"💬 主聊天室\n🏷️ 群組: {chat_title}\n🔢 識別碼: {thread_key}\n\n"
            else:
                thread_name = get_thread_name(chat_id, thread_id)
                thread_list += f"💬 話題: {thread_name}\n🏷️ 群組: {chat_title}\n🔢 識別碼: {thread_key}\n\n"
        except:
            thread_list += f"💬 話題\n🔢 識別碼: {thread_key}\n\n"
    
    return thread_list

# ========== Telegram API ==========
def send_message(chat_id, text, markup=None, thread_id=None):
    try:
        payload = {'chat_id': chat_id, 'text': text}
        if thread_id: payload['message_thread_id'] = thread_id
        if markup: payload['reply_markup'] = json.dumps(markup)
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload, timeout=5)
    except:
        pass

def answer_callback(callback_id):
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", 
                     json={'callback_query_id': callback_id}, timeout=5)
    except:
        pass

# ========== 處理函數 ==========
def handle_uid_query(update, chat_id):
    try:
        user = update['message']['forward_from']
        name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "未知"
        username = f"@{user.get('username')}" if user.get('username') else "未設定"
        
        text = f"""🔍 用戶 UID 查詢結果

👤 姓名：{name}
🔢 UID：{user['id']}
📧 用戶名：{username}"""

        markup = {
            "inline_keyboard": [
                [{"text": "📋 複製UID", "callback_data": f"copy_{user['id']}"}],
                [{"text": "➕ 新增此用戶為管理員", "callback_data": f"add_{user['id']}"}],
                [{"text": "🔙 管理員面板", "callback_data": "admin_menu"}]
            ]
        }
        send_message(chat_id, text, markup)
    except:
        send_message(chat_id, "❌ 查詢失敗")

def handle_admin_command(text, chat_id, user_id, update=None):
    if text == '/admin':
        send_message(chat_id, "👑 管理員控制面板", admin_menu(user_id))
    
    elif text.startswith('/admin add_admin '):
        try:
            new_id = int(text.split(' ')[2])
            if add_admin(new_id, user_id):
                send_message(chat_id, f"✅ 已新增管理員: {new_id}")
                log_action(user_id, "add_admin", new_id)
            else:
                send_message(chat_id, f"❌ 用戶 {new_id} 已經是管理員")
        except:
            send_message(chat_id, "❌ 請提供有效的用戶ID")
    
    elif text.startswith('/admin remove_admin '):
        try:
            remove_id = int(text.split(' ')[2])
            if remove_admin(remove_id):
                send_message(chat_id, f"✅ 已移除管理員: {remove_id}")
                log_action(user_id, "remove_admin", remove_id)
            else:
                send_message(chat_id, "❌ 該用戶不是管理員或是超級管理員")
        except:
            send_message(chat_id, "❌ 請提供有效的用戶ID")
    
    elif text == '/admin list_admins':
        send_message(chat_id, get_admin_list_with_names())
    
    elif text == '/admin list_threads':
        send_message(chat_id, get_thread_list_with_names())
    
    elif text.startswith('/admin logs') and is_super_admin(user_id):
        logs = get_logs()[-10:]
        if not logs:
            send_message(chat_id, "📊 目前沒有操作紀錄")
        else:
            msg = "📊 最近操作紀錄：\n\n"
            for log in reversed(logs):
                time = datetime.datetime.fromisoformat(log['timestamp']).strftime("%m/%d %H:%M")
                admin_name = log.get('admin_name', log['admin_id'])
                action_text = f"{log['action']}"
                if log['target_id']:
                    target_name = log.get('target_name', log['target_id'])
                    action_text += f" → {target_name}"
                msg += f"⏰ {time} | 👤 {admin_name} | {action_text}\n"
            send_message(chat_id, msg)

def handle_group_admin(text, chat_id, user_id, update):
    thread_id = update['message'].get('message_thread_id', 0)
    
    if text == '/admin add_thread':
        if toggle_thread(chat_id, thread_id, True):
            send_message(chat_id, "✅ 已允許當前話題", None, thread_id)
            log_action(user_id, "add_thread", details=f"{chat_id}_{thread_id}")
        else:
            send_message(chat_id, "❌ 操作失敗", None, thread_id)
    
    elif text == '/admin remove_thread':
        if toggle_thread(chat_id, thread_id, False):
            send_message(chat_id, "❌ 已移除話題權限", None, thread_id)
            log_action(user_id, "remove_thread", details=f"{chat_id}_{thread_id}")
        else:
            send_message(chat_id, "❌ 此話題未被允許", None, thread_id)

def handle_user_command(text, chat_id, is_private, update=None):
    # 修正：處理帶有 @bot_username 的指令
    clean_text = text.split('@')[0] if '@' in text else text
    
    thread_id = None
    if not is_private and update and 'message' in update:
        thread_id = update['message'].get('message_thread_id')
    
    if clean_text == '/start':
        send_message(chat_id, "🐾 歡迎使用10K DOG 官方BOT", main_menu(), thread_id)
    
    elif clean_text == '/help':
        send_message(chat_id, HELP_TEXT, None, thread_id)
    
    elif clean_text.startswith('/'):
        cmd = clean_text[1:].lower().split(' ')[0]
        if cmd in COMMANDS:
            send_message(chat_id, COMMANDS[cmd], None, thread_id)

def handle_callback(data, chat_id, user_id, message_thread_id=None):
    # 修正：檢查群組話題權限
    if str(chat_id).startswith('-100'):
        thread_key = f"{chat_id}_{message_thread_id or 0}"
        if thread_key not in get_threads() and not data.startswith(('admin_', 'main_menu', 'help')):
            send_message(chat_id, "❌ 此話題未啟用機器人功能", None, message_thread_id)
            return
    
    if data in COMMANDS:
        send_message(chat_id, COMMANDS[data], None, message_thread_id)
    
    elif data == 'help':
        send_message(chat_id, HELP_TEXT, None, message_thread_id)
    
    elif data == 'main_menu':
        send_message(chat_id, "🐾 歡迎使用10K DOG 官方BOT", main_menu())
    
    elif data == 'admin_menu':
        send_message(chat_id, "👑 管理員控制面板", admin_menu(user_id))
    
    elif data == 'admin_list':
        send_message(chat_id, get_admin_list_with_names())
    
    elif data == 'admin_query_uid':
        send_message(chat_id, "🔍 請轉發用戶訊息給我查詢 UID")
    
    elif data == 'admin_add':
        send_message(chat_id, "➕ 請直接輸入要新增的用戶 UID 數字")
    
    elif data == 'admin_remove':
        send_message(chat_id, "❌ 請直接輸入要移除的用戶 UID 數字")
    
    elif data == 'admin_threads':
        send_message(chat_id, get_thread_list_with_names())
    
    elif data == 'admin_help':
        send_message(chat_id, "🛠️ 群組指令：\n/admin add_thread - 允許話題\n/admin remove_thread - 移除話題")
    
    elif data == 'admin_logs' and is_super_admin(user_id):
        logs = get_logs()[-10:]
        if not logs:
            send_message(chat_id, "📊 目前沒有操作紀錄")
        else:
            msg = "📊 最近操作紀錄：\n\n"
            for log in reversed(logs):
                time = datetime.datetime.fromisoformat(log['timestamp']).strftime("%m/%d %H:%M")
                admin_name = log.get('admin_name', log['admin_id'])
                action_text = f"{log['action']}"
                if log['target_id']:
                    target_name = log.get('target_name', log['target_id'])
                    action_text += f" → {target_name}"
                msg += f"⏰ {time} | 👤 {admin_name} | {action_text}\n"
            send_message(chat_id, msg)
    
    elif data.startswith('copy_'):
        send_message(chat_id, data.replace('copy_', ''))
    
    elif data.startswith('add_') and is_super_admin(user_id):
        try:
            uid = int(data.replace('add_', ''))
            if add_admin(uid, user_id):
                send_message(chat_id, f"✅ 已新增用戶 {uid} 為管理員")
                log_action(user_id, "add_admin", uid)
            else:
                send_message(chat_id, f"❌ 用戶 {uid} 已經是管理員")
        except:
            send_message(chat_id, "❌ 操作失敗")

# ========== 處理 UID 數字輸入 ==========
def handle_uid_input(text, chat_id, user_id):
    try:
        uid = int(text.strip())
        if add_admin(uid, user_id):
            send_message(chat_id, f"✅ 已新增管理員: {uid}")
            log_action(user_id, "add_admin", uid)
        else:
            send_message(chat_id, f"❌ 用戶 {uid} 已經是管理員")
    except ValueError:
        send_message(chat_id, "❌ 請輸入有效的數字 UID")

# ========== 主路由 ==========
@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    
    # 處理回調查詢
    if 'callback_query' in update:
        cb = update['callback_query']
        data, chat_id, user_id = cb['data'], cb['message']['chat']['id'], cb['from']['id']
        thread_id = None if not str(chat_id).startswith('-100') else cb['message'].get('message_thread_id')
        
        handle_callback(data, chat_id, user_id, thread_id)
        answer_callback(cb['id'])
        return 'OK'
    
    # 處理文字訊息
    if 'message' in update and 'text' in update['message']:
        msg = update['message']
        text, chat_id, user_id = msg['text'], msg['chat']['id'], msg['from']['id']
        is_private = not str(chat_id).startswith('-100')
        
        # UID 查詢
        if 'forward_from' in msg and not text.startswith('/') and is_admin(user_id):
            handle_uid_query(update, chat_id)
            return 'OK'
        
        # 管理員 UID 輸入處理
        if is_private and is_admin(user_id) and text.strip().isdigit():
            handle_uid_input(text, chat_id, user_id)
            return 'OK'
        
        # 權限檢查
        if not is_private and not should_process(update, user_id, text):
            return 'OK'
        
        # 管理員命令
        if is_admin(user_id) and text.startswith('/admin'):
            if is_private:
                handle_admin_command(text, chat_id, user_id, update)
            else:
                handle_group_admin(text, chat_id, user_id, update)
        
        # 一般用戶命令
        else:
            handle_user_command(text, chat_id, is_private, update)
    
    return 'OK'

@app.route('/')
def home():
    return "🤖 10K DOG Bot is Running!"

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    webhook_url = f"https://{request.host}/webhook"
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
    return requests.get(url).json()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
