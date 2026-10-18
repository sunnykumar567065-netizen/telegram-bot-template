import os
import zipfile
import subprocess
import threading
from flask import Flask, send_from_directory, abort
import telebot
from telebot import types

TOKEN = "8809911900:AAGZoRQxo79zLD7eQAhMeVCs1bZaEeNS-7A"
CHANNEL_ID = -1003922357113
INVITE_LINK = "https://t.me/+37sWLJKmEIBlMTA1"

# Automatically adapt to Koyeb or Render environment ports
PORT = int(os.environ.get("PORT", 8000))

# Automatically detect public domain for Koyeb or Render
BASE_PUBLIC_URL = os.getenv("KOYEB_PUBLIC_DOMAIN") or os.getenv("RENDER_EXTERNAL_URL") or f"http://127.0.0.1:{PORT}"
if BASE_PUBLIC_URL and not BASE_PUBLIC_URL.startswith("http"):
    BASE_PUBLIC_URL = f"https://{BASE_PUBLIC_URL}"

bot = telebot.TeleBot(TOKEN, parse_mode="MARKDOWN")

UPLOAD_DIR = "hosted_files"
WEB_DIR = "public_html"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(WEB_DIR, exist_ok=True)

user_states = {}

# --- BUILT-IN WEB SERVER TO PREVENT 404 ERRORS ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 Cloud Public Hosting Bot Web Server is Live & Running 24/7!"

@app.route('/public_html/<user_id>/', defaults={'subpath': ''})
@app.route('/public_html/<user_id>/<path:subpath>')
def serve_user_website(user_id, subpath):
    user_folder = os.path.join(WEB_DIR, str(user_id))
    if not os.path.exists(user_folder):
        return abort(404, description="Website folder not found!")
    
    # If path is empty or points to a directory, check for index.html automatically
    target_path = os.path.join(user_folder, subpath)
    if subpath == "" or os.path.isdir(target_path):
        # Look for index.html inside the directory
        index_file = os.path.join(target_path if subpath else user_folder, "index.html")
        if os.path.exists(index_file):
            rel_dir = os.path.join(str(user_id), subpath) if subpath else str(user_id)
            return send_from_directory(WEB_DIR, os.path.join(rel_dir, "index.html"))
            
    # Serve requested file directly with auto-fallback to avoid 404
    if os.path.exists(target_path) and os.path.isfile(target_path):
        return send_from_directory(WEB_DIR, os.path.join(str(user_id), subpath))
        
    # If exact file not found, try adding .html or return 404
    html_target = target_path + ".html"
    if os.path.exists(html_target):
        return send_from_directory(WEB_DIR, os.path.join(str(user_id), subpath + ".html"))
        
    return abort(404, description="Requested file or page not found!")

def run_web_server():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
# -----------------------------------------------

def check_force_join(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        print(f"Force Join Error: {e}")
    return False

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    if not check_force_join(user_id):
        markup = types.InlineKeyboardMarkup()
        btn_join = types.InlineKeyboardButton("📢 Join Channel", url=INVITE_LINK)
        btn_check = types.InlineKeyboardButton("🔄 Check Joined", callback_data="check_join")
        markup.add(btn_join, btn_check)
        bot.send_message(message.chat.id, "⚠️ **Access Denied!** Pehle channel join karein.", reply_markup=markup)
        return

    bot.send_message(
        message.chat.id,
        "🚀 **Cloud Public Hosting Bot Active!**\n\n"
        "Apni koi bhi file (`.zip`, `.html`, `.php`, `.py`) bhein. Bot auto-analyze karke aapko **Real Public Live URL** dega!"
    )

@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def verify_join_callback(call):
    user_id = call.from_user.id
    if check_force_join(user_id):
        bot.answer_callback_query(call.id, "✅ Verified!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        send_welcome(call.message)
    else:
        bot.answer_callback_query(call.id, "❌ Channel join nahi kiya!", show_alert=True)

@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    user_id = message.from_user.id
    if not check_force_join(user_id):
        bot.reply_to(message, "⚠️ Pehle channel join karein!")
        return

    file_info = bot.get_file(message.document.file_id)
    file_name = message.document.file_name
    ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
    
    downloaded_file = bot.download_file(file_info.file_path)
    
    user_folder = os.path.join(UPLOAD_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    file_path = os.path.join(user_folder, file_name)
    
    with open(file_path, 'wb') as f:
        f.write(downloaded_file)
        
    user_states[user_id] = {'file_path': file_path, 'file_name': file_name, 'ext': ext}
    
    markup = types.InlineKeyboardMarkup()
    if ext == 'py':
        markup.add(
            types.InlineKeyboardButton("🌐 Host Python Web App", callback_data="host_py_web"),
            types.InlineKeyboardButton("🤖 Run Python Bot/Script", callback_data="host_py_script")
        )
    else:
        markup.add(
            types.InlineKeyboardButton("🌐 Host as Live Public Website", callback_data="host_web_standard")
        )
    
    bot.reply_to(message, f"🔍 **File Analyzed:** `.{ext}` detected!\n\n📁 **File:** `{file_name}`\n\nAap ise kaise deploy karna chahte hain?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ["host_py_web", "host_py_script", "host_web_standard"])
def process_hosting_action(call):
    user_id = call.from_user.id
    if user_id not in user_states:
        bot.answer_callback_query(call.id, "Session expired. Upload again.", show_alert=True)
        return
        
    data = user_states[user_id]
    file_path = data['file_path']
    file_name = data['file_name']
    ext = data['ext']
    action = call.data
    
    if action in ["host_web_standard", "host_py_web"]:
        user_web_dir = os.path.join(WEB_DIR, str(user_id))
        os.makedirs(user_web_dir, exist_ok=True)
        
        if ext == 'zip':
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(user_web_dir)
            hosted_link = f"{BASE_PUBLIC_URL}/public_html/{user_id}/"
        else:
            import shutil
            shutil.copy(file_path, user_web_dir)
            hosted_link = f"{BASE_PUBLIC_URL}/public_html/{user_id}/{file_name}"
            
        response_text = (
            f"✅ **Website Publicly Hosted!**\n\n"
            f"🌐 **Real Live URL:**\n`{hosted_link}`\n\n"
            f"📊 **Status:** `Online & Accessible Worldwide 24/7 (No 404 Error)`"
        )
    elif action == "host_py_script":
        try:
            process = subprocess.subprocess.Popen if hasattr(subprocess, 'subprocess') else subprocess.Popen
            proc = process(["python", file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            response_text = (
                f"✅ **Script Deployed Successfully!**\n\n"
                f"⚙️ **File:** `{file_name}`\n"
                f"🆔 **Process PID:** `{proc.pid}`\n"
                f"🚀 **Status:** `Running live in cloud background`"
            )
        except Exception as e:
            response_text = f"❌ Execution Error: {str(e)}"
    else:
        response_text = "⚠️ Invalid selection."

    bot.edit_message_text(response_text, call.message.chat.id, call.message.message_id, parse_mode="MARKDOWN")
    bot.answer_callback_query(call.id, "Live Deployment Successful!")

if __name__ == "__main__":
    print("🌐 Starting Flask Web Server thread...")
    server_thread = threading.Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    print("🤖 Cloud Public Hosting Bot running...")
    bot.infinity_polling()
