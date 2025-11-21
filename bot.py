import os
import json
from flask import Flask, request
import requests
import datetime
import pytz

app = Flask(__name__)
TOKEN = os.getenv("BOT_TOKEN")

# 超級管理員 ID（替換為您的 Telegram User ID）
SUPER_ADMIN = 8126033106  # 請替換為您的實際 ID

# 資料儲存檔案 - 使用絕對路徑確保在 Vercel 上可寫
DATA_FILE = "/tmp/admin_data.json" if os.path.exists('/tmp') else "admin_data.json"

# 初始化資料
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"載入資料錯誤：{e}")
    
    # 預設資料結構
    default_data = {
        "admins": {
            str(SUPER_ADMIN): {
                "added_by": "system",
                "added_time": datetime.datetime.now(TAIWAN_TZ).isoformat(),
                "is_super": True
            }
        },
        "allowed_threads": {},
        "admin_logs": []
    }
    save_data(default_data)
    return default_data

def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"儲存資料錯誤：{e}")

# 載入初始資料
data = load_data()
ADMINS = data.get("admins", {})
ALLOWED_THREADS = data.get("allowed_threads", {})
ADMIN_LOGS = data.get("admin_logs", [])

# 台灣時區
TAIWAN_TZ = pytz.timezone('Asia/Taipei')

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
    return str(user_id) in ADMINS

def is_super_admin(user_id):
    admin_info = ADMINS.get(str(user_id), {})
    return admin_info.get('is_super', False)

# 操作記錄函數
def log_admin_action(admin_id, action, target_id=None, details=None):
    taiwan_time = datetime.datetime.now(TAIWAN_TZ)
    log_entry = {
        'timestamp': taiwan_time.isoformat(),
        'admin_id': admin_id,
        'action': action,
        'target_id': target_id,
        'details': details
    }
    ADMIN_LOGS.append(log_entry)
    if len(ADMIN_LOGS) > 500:
        ADMIN_LOGS.pop(0)
    
    # 自動儲存到資料庫
    data["admin_logs"] = ADMIN_LOGS
    save_data(data)

# 新增管理員函數
def add_admin(admin_id, added_by, is_super=False):
    try:
        admin_id_str = str(admin_id)
        if admin_id_str not in ADMINS:
            ADMINS[admin_id_str] = {
                "added_by": added_by,
                "added_time": datetime.datetime.now(TAIWAN_TZ).isoformat(),
                "is_super": is_super
            }
            # 自動儲存到資料庫
            data["admins"] = ADMINS
            save_data(data)
            return True
        return False
    except Exception as e:
        print(f"新增管理員錯誤：{e}")
        return False

# 移除管理員函數
def remove_admin(admin_id):
    try:
        admin_id_str = str(admin_id)
        if admin_id_str in ADMINS and not ADMINS[admin_id_str].get('is_super', False):
            del ADMINS[admin_id_str]
            # 自動儲存到資料庫
            data["admins"] = ADMINS
            save_data(data)
            return True
        return False
    except Exception as e:
        print(f"移除管理員錯誤：{e}")
        return False

# 更新話題函數
def update_allowed_threads():
    data["allowed_threads"] = ALLOWED_THREADS
    save_data(data)

# 權限檢查函數
def should_process_message(update, user_id, message_text):
    chat_id = update['message']['chat']['id']
    thread_id = update['message'].get('message_thread_id')
    
    thread_key = f"{chat_id}_{thread_id if thread_id else 0}"
    
    if (is_admin(user_id) and 
        message_text in ['/admin add_thread', '/admin remove_thread']):
        return True
    
    return thread_key in ALLOWED_THREADS

# 設定命令清單
def set_bot_commands():
    try:
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
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"設定命令清單錯誤：{e}")

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
        [{"text": "👥 管理員列表", "callback_data": "private_list_admins"}, 
         {"text": "🔍 查詢TG UID", "callback_data": "private_query_uid"}],
        [{"text": "➕ 新增管理員", "callback_data": "private_add_admin_input"}, 
         {"text": "❌ 移除管理員", "callback_data": "private_remove_admin_input"}],
        [{"text": "📋 話題列表", "callback_data": "private_list_threads"}, 
         {"text": "🛠️ 群組指令說明", "callback_data": "private_group_commands"}],
    ]
    
    if is_super_admin(user_id):
        keyboard.append([{"text": "📊 操作紀錄", "callback_data": "private_view_logs"}])
    
    keyboard.append([{"text": "🔙 主選單", "callback_data": "private_back_to_main"}])
    
    return {"inline_keyboard": keyboard}

# 群組管理指令處理
def handle_group_admin_command(message_text, chat_id, user_id, update):
    try:
        thread_id = update['message'].get('message_thread_id')
        thread_key = f"{chat_id}_{thread_id if thread_id else 0}"
        
        if message_text == '/admin add_thread':
            ALLOWED_THREADS[thread_key] = True
            send_message(chat_id, "✅ 已允許當前話題", None, thread_id)
            log_admin_action(user_id, "add_thread", details=thread_key)
            update_allowed_threads()
                
        elif message_text == '/admin remove_thread':
            if thread_key in ALLOWED_THREADS:
                del ALLOWED_THREADS[thread_key]
                send_message(chat_id, "❌ 已移除當前話題權限", None, thread_id)
                log_admin_action(user_id, "remove_thread", details=thread_key)
                update_allowed_threads()
            else:
                send_message(chat_id, "❌ 此話題未被允許", None, thread_id)
        
        elif message_text == '/admin':
            pass
            
    except Exception as e:
        print(f"群組管理指令錯誤：{e}")

# 私聊管理員命令處理
def handle_private_admin_command(message_text, chat_id, user_id):
    try:
        if message_text.startswith('/admin add_admin '):
            parts = message_text.split(' ')
            if len(parts) > 2:
                try:
                    new_admin_id = int(parts[2])
                    if add_admin(new_admin_id, user_id):
                        send_message(chat_id, f"✅ 已新增管理員: {new_admin_id}")
                        log_admin_action(user_id, "add_admin", target_id=new_admin_id)
                    else:
                        send_message(chat_id, f"❌ 用戶 {new_admin_id} 已經是管理員")
                except ValueError:
                    send_message(chat_id, "❌ 請提供有效的用戶ID")
                    
        elif message_text.startswith('/admin remove_admin '):
            parts = message_text.split(' ')
            if len(parts) > 2:
                try:
                    remove_admin_id = int(parts[2])
                    if remove_admin(remove_admin_id):
                        send_message(chat_id, f"❌ 已移除管理員: {remove_admin_id}")
                        log_admin_action(user_id, "remove_admin", target_id=remove_admin_id)
                    else:
                        send_message(chat_id, "❌ 該用戶不是管理員或是超級管理員")
                except ValueError:
                    send_message(chat_id, "❌ 請提供有效的用戶ID")
                    
        elif message_text == '/admin list_admins':
            admin_list = get_admin_list_with_names()
            send_message(chat_id, admin_list)
            
        elif message_text == '/admin list_threads':
            thread_list = get_thread_list_with_names()
            send_message(chat_id, thread_list)
            
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
            
        elif message_text == '/admin myid':
            send_message(chat_id, f"🔢 您的 User ID 是: `{user_id}`")
            
    except Exception as e:
        print(f"私聊管理員命令錯誤：{e}")
        send_message(chat_id, "❌ 命令處理失敗，請稍後再試")

# 獲取管理員列表
def get_admin_list_with_names():
    if not ADMINS:
        return "👥 目前沒有管理員"
    
    admin_list = "👥 管理員列表：\n\n"
    for admin_id, admin_info in ADMINS.items():
        try:
            user_info = get_user_info(int(admin_id))
            if user_info:
                first_name = user_info.get('first_name', '')
                last_name = user_info.get('last_name', '')
                username = user_info.get('username', '')
                
                full_name = f"{first_name} {last_name}".strip()
                if not full_name:
                    full_name = "未知用戶"
                
                username_display = f"(@{username})" if username else "(無用戶名)"
                role = "👑 超級管理員" if admin_info.get('is_super', False) else "👤 管理員"
                added_time = admin_info.get('added_time', '未知時間')
                
                # 格式化時間
                try:
                    added_dt = datetime.datetime.fromisoformat(added_time).astimezone(TAIWAN_TZ)
                    time_str = added_dt.strftime("%Y/%m/%d %H:%M")
                except:
                    time_str = added_time
                
                admin_list += f"{role} - {full_name} {username_display}\n"
                admin_list += f"🔢 ID: `{admin_id}`\n"
                admin_list += f"⏰ 新增時間: {time_str}\n\n"
            else:
                admin_list += f"👤 未知用戶\n🔢 ID: `{admin_id}`\n\n"
        except:
            admin_list += f"👤 未知用戶\n🔢 ID: `{admin_id}`\n\n"
    
    return admin_list

# 獲取話題列表
def get_thread_list_with_names():
    if not ALLOWED_THREADS:
        return "📋 目前沒有允許的話題"
    
    thread_list = "📋 允許的話題列表：\n\n"
    for thread_key in ALLOWED_THREADS.keys():
        chat_id, thread_id = thread_key.split('_')
        thread_id = int(thread_id) if thread_id != '0' else 0
        
        try:
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

# 獲取用戶資訊
def get_user_info(user_id):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getChat"
        payload = {"chat_id": user_id}
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json().get('result', {})
    except:
        pass
    return None

# 獲取聊天資訊
def get_chat_info(chat_id):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getChat"
        payload = {"chat_id": chat_id}
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json().get('result', {})
    except:
        pass
    return None

# 獲取話題名稱
def get_thread_name(chat_id, thread_id):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getForumTopic"
        payload = {
            "chat_id": chat_id,
            "message_thread_id": thread_id
        }
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return response.json().get('result', {}).get('name', '未知話題')
    except:
        pass
    return '未知話題'

# 超級管理員專屬命令
def handle_super_admin_commands(message_text, chat_id, user_id):
    try:
        if message_text.startswith('/admin logs'):
            parts = message_text.split(' ')
            count = int(parts[2]) if len(parts) > 2 else 10
            
            logs = ADMIN_LOGS[-count:] if count <= len(ADMIN_LOGS) else ADMIN_LOGS
            if not logs:
                send_message(chat_id, "📊 目前沒有操作紀錄")
            else:
                log_text = "📊 最近管理操作紀錄：\n\n"
                
                for log in reversed(logs):
                    taiwan_time = datetime.datetime.fromisoformat(log['timestamp']).astimezone(TAIWAN_TZ)
                    time_str = taiwan_time.strftime("%m/%d %H:%M")
                    
                    log_text += f"⏰ 時間: {time_str}\n"
                    log_text += f"👤 管理員: {log['admin_id']}\n"
                    log_text += f"📝 操作: {log['action']}\n"
                    
                    if log['target_id']:
                        log_text += f"🎯 目標: {log['target_id']}\n"
                    
                    if log['details']:
                        log_text += f"📋 詳情: {log['details']}\n"
                    
                    log_text += "─" * 20 + "\n\n"
                
                send_message(chat_id, log_text)
                
    except Exception as e:
        print(f"超級管理員命令錯誤：{e}")
        send_message(chat_id, "❌ 操作紀錄查詢失敗")

# UID 查詢處理函數
def handle_uid_query(update, chat_id):
    try:
        forwarded_user = update['message']['forward_from']
        forwarded_user_id = forwarded_user['id']
        forwarded_first_name = forwarded_user.get('first_name', '')
        forwarded_last_name = forwarded_user.get('last_name', '')
        forwarded_username = forwarded_user.get('username', '')
        
        full_name = forwarded_first_name
        if forwarded_last_name:
            full_name += f" {forwarded_last_name}"
        if not full_name:
            full_name = "未知"
        
        user_info = f"""🔍 **用戶 UID 查詢結果**

👤 **姓名：** {full_name}
🔢 **UID：** `{forwarded_user_id}`
📧 **用戶名：** @{forwarded_username if forwarded_username else '未設定'}"""

        copy_keyboard = {
            "inline_keyboard": [
                [{"text": "📋 複製UID", "callback_data": f"copy_uid_{forwarded_user_id}"}],
                [{"text": "➕ 新增此用戶為管理員", "callback_data": f"add_this_user_{forwarded_user_id}"}],
                [{"text": "🔙 返回管理員面板", "callback_data": "private_back_to_admin"}]
            ]
        }
        
        send_message(chat_id, user_info, copy_keyboard)
        
    except Exception as e:
        print(f"UID查詢錯誤：{e}")
        send_message(chat_id, "❌ 查詢失敗，請確保轉發的是用戶訊息且隱私設定允許")

# UID 查詢按鈕處理函數
def handle_uid_query_buttons(callback_data, chat_id, user_id):
    try:
        if callback_data.startswith('copy_uid_'):
            uid_to_copy = callback_data.replace('copy_uid_', '')
            send_message(chat_id, f"📋 請複製以下 UID：\n\n`{uid_to_copy}`")
            
        elif callback_data.startswith('add_this_user_'):
            if is_super_admin(user_id):
                uid_to_add = int(callback_data.replace('add_this_user_', ''))
                if add_admin(uid_to_add, user_id):
                    send_message(chat_id, f"✅ 已新增用戶 {uid_to_add} 為管理員")
                    log_admin_action(user_id, "add_admin", target_id=uid_to_add)
                else:
                    send_message(chat_id, f"❌ 用戶 {uid_to_add} 已經是管理員")
            else:
                send_message(chat_id, "❌ 只有超級管理員可以新增管理員")
                
    except ValueError:
        send_message(chat_id, "❌ UID 格式錯誤")
    except Exception as e:
        print(f"UID按鈕處理錯誤：{e}")
        send_message(chat_id, "❌ 操作失敗，請稍後再試")

# 私聊管理員按鈕處理
def handle_private_admin_button(callback_data, chat_id, user_id):
    try:
        if callback_data == 'private_list_admins':
            admin_list = get_admin_list_with_names()
            send_message(chat_id, admin_list)
            
        elif callback_data == 'private_query_uid':
            help_text = """🔍 **查詢用戶 UID**

請轉發該用戶的任意一則訊息給我，我將回覆：
• 用戶基本資訊
• UID 數字
• 複製按鈕
• 一鍵新增管理員按鈕

📝 **使用步驟：**
1. 長按用戶訊息選擇「轉發」
2. 選擇這個機器人傳送
3. 即可獲得 UID 用戶相關資訊"""
            send_message(chat_id, help_text)
            
        elif callback_data == 'private_add_admin_input':
            help_text = """➕ **新增管理員**

請直接貼上要新增的用戶 UID：

例如：
`123456789`

或者使用「🔍 查詢TG UID」功能獲取 UID 後，使用「➕ 新增此用戶為管理員」按鈕"""
            send_message(chat_id, help_text)
            
        elif callback_data == 'private_remove_admin_input':
            help_text = """❌ **移除管理員**

請直接貼上要移除的用戶 UID：

例如：
`123456789`

💡 可以使用「👥 管理員列表」查看當前所有管理員"""
            send_message(chat_id, help_text)
            
        elif callback_data == 'private_list_threads':
            thread_list = get_thread_list_with_names()
            send_message(chat_id, thread_list)
            
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
                    taiwan_time = datetime.datetime.fromisoformat(log['timestamp']).astimezone(TAIWAN_TZ)
                    time_str = taiwan_time.strftime("%m/%d %H:%M")
                    
                    log_text += f"⏰ 時間: {time_str}\n"
                    log_text += f"👤 管理員: {log['admin_id']}\n"
                    log_text += f"📝 操作: {log['action']}\n"
                    
                    if log['target_id']:
                        log_text += f"🎯 目標: {log['target_id']}\n"
                    
                    if log['details']:
                        log_text += f"📋 詳情: {log['details']}\n"
                    
                    log_text += "─" * 20 + "\n\n"
                send_message(chat_id, log_text)
            
        elif callback_data == 'private_back_to_main':
            send_message(chat_id, "🐾 歡迎使用10K DOG 官方BOT", create_reply_markup())
            
        elif callback_data == 'private_back_to_admin':
            menu_text = "👑 管理員控制面板"
            markup = create_private_admin_markup(user_id)
            send_message(chat_id, menu_text, markup)
            
    except Exception as e:
        print(f"管理員按鈕處理錯誤：{e}")
        send_message(chat_id, "❌ 操作失敗，請稍後再試")

# 處理管理員輸入的 UID
def handle_admin_uid_input(message_text, chat_id, user_id):
    try:
        uid_text = message_text.strip()
        
        if not uid_text.isdigit():
            send_message(chat_id, "❌ 請輸入有效的數字 UID")
            return
        
        target_uid = int(uid_text)
        
        if "新增" in message_text or "add" in message_text.lower():
            if add_admin(target_uid, user_id):
                send_message(chat_id, f"✅ 已新增管理員: {target_uid}")
                log_admin_action(user_id, "add_admin", target_id=target_uid)
            else:
                send_message(chat_id, f"❌ 用戶 {target_uid} 已經是管理員")
                
        elif "移除" in message_text or "remove" in message_text.lower() or "刪除" in message_text:
            if remove_admin(target_uid):
                send_message(chat_id, f"❌ 已移除管理員: {target_uid}")
                log_admin_action(user_id, "remove_admin", target_id=target_uid)
            else:
                send_message(chat_id, "❌ 該用戶不是管理員或是超級管理員")
        else:
            if add_admin(target_uid, user_id):
                send_message(chat_id, f"✅ 已新增管理員: {target_uid}")
                log_admin_action(user_id, "add_admin", target_id=target_uid)
            else:
                send_message(chat_id, f"❌ 用戶 {target_uid} 已經是管理員")
                
    except ValueError:
        send_message(chat_id, "❌ 請提供有效的用戶ID")
    except Exception as e:
        print(f"管理員UID輸入處理錯誤：{e}")
        send_message(chat_id, "❌ 操作失敗，請稍後再試")

# 一般用戶命令處理
def handle_user_commands(message_text, chat_id, user_id, is_private):
    try:
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
                pass
                
    except Exception as e:
        print(f"一般用戶命令錯誤：{e}")

# 主 webhook 處理
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        if ('message' in update and 
            'forward_from' in update['message'] and 
            not update['message']['text'].startswith('/')):
            
            chat_id = update['message']['chat']['id']
            user_id = update['message']['from']['id']
            
            if is_admin(user_id):
                handle_uid_query(update, chat_id)
                return 'OK'
        
        elif 'callback_query' in update:
            callback_data = update['callback_query']['data']
            chat_id = update['callback_query']['message']['chat']['id']
            user_id = update['callback_query']['from']['id']
            is_private = not str(chat_id).startswith('-100')
            
            if callback_data in COMMANDS:
                send_message(chat_id, COMMANDS[callback_data])
            elif callback_data == 'help':
                help_text = "📋 所有可用指令：\n" + "\n".join([f"/{cmd}" for cmd in COMMANDS.keys()])
                send_message(chat_id, help_text)
            
            elif is_private and callback_data.startswith('private_'):
                handle_private_admin_button(callback_data, chat_id, user_id)
            
            elif is_private and (callback_data.startswith('copy_uid_') or callback_data.startswith('add_this_user_')):
                handle_uid_query_buttons(callback_data, chat_id, user_id)
            
            answer_callback_query(update['callback_query']['id'])
            return 'OK'
        
        elif 'message' in update and 'text' in update['message']:
            message_text = update['message']['text']
            chat_id = update['message']['chat']['id']
            user_id = update['message']['from']['id']
            is_private = not str(chat_id).startswith('-100')
            
            if message_text.startswith('/admin') and not is_admin(user_id):
                return 'OK'
            
            if not is_private and not should_process_message(update, user_id, message_text):
                return 'OK'
            
            if is_admin(user_id):
                if is_private:
                    if message_text == '/admin':
                        menu_text = "👑 管理員控制面板"
                        markup = create_private_admin_markup(user_id)
                        send_message(chat_id, menu_text, markup)
                    elif message_text.startswith('/admin '):
                        if is_super_admin(user_id) and message_text.startswith('/admin logs'):
                            handle_super_admin_commands(message_text, chat_id, user_id)
                        else:
                            handle_private_admin_command(message_text, chat_id, user_id)
                    elif message_text.strip().isdigit():
                        handle_admin_uid_input(message_text, chat_id, user_id)
                else:
                    handle_group_admin_command(message_text, chat_id, user_id, update)
            
            else:
                handle_user_commands(message_text, chat_id, user_id, is_private)
        
        return 'OK'
    except Exception as e:
        print(f"webhook 錯誤：{e}")
        return 'OK'

def answer_callback_query(callback_query_id):
    try:
        url = f'https://api.telegram.org/bot{TOKEN}/answerCallbackQuery'
        payload = {'callback_query_id': callback_query_id}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"回答回調查詢錯誤：{e}")

def send_message(chat_id, text, reply_markup=None, thread_id=None):
    try:
        url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown'
        }
        if thread_id:
            payload['message_thread_id'] = thread_id
        if reply_markup:
            payload['reply_markup'] = json.dumps(reply_markup)
        
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"發送訊息錯誤：{e}")

@app.route('/')
def home():
    return "🤖 10K DOG Bot is Running!"

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        webhook_url = f"https://{request.host}/webhook"
        url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={webhook_url}"
        response = requests.get(url, timeout=10)
        set_bot_commands()
        return response.json()
    except Exception as e:
        print(f"設定 webhook 錯誤：{e}")
        return {"error": str(e)}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)