import os
import logging
import re
import sqlite3
from datetime import datetime
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ.get("TOKEN")

# --- FLASK WEB SERVER (Stable for Render Cloud) ---
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Cleaning Bot is active and running!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)

web_thread = Thread(target=run_web_server, daemon=True)
web_thread.start()

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('cleaning_records.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cleanings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_key TEXT,
            display_name TEXT,
            cleaning_date TEXT,
            month_year TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def normalize_unit(text):
    """
    Applies your rule: Extracts letters and numbers, strips all zeros from digits 
    so variations like A-17-05, a1705, A175, and A-17-5 all map to the same unit.
    """
    if not text:
        return None, None
        
    # Find all letters for the prefix (e.g., 'A')
    letters = "".join(re.findall(r'[a-zA-Z]', text)).upper()
    # Find all digits in the text
    digits = "".join(re.findall(r'\d', text))
    
    if not digits:
        return None, None
        
    # Strip all zeros from digits to normalize variations
    digits_no_zero = digits.replace('0', '')
    
    # Create a unique database key
    unit_key = f"{letters}-{digits_no_zero}" if letters else digits_no_zero
    
    # Clean display name for the chat response (e.g., use the raw matched token or uppercase text)
    display_name = text.strip()
    
    return unit_key, display_name

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    text = message.caption or message.text
    if not text:
        return

    unit_key, display_name = normalize_unit(text)
    if not unit_key:
        return 

    now = datetime.now()
    cleaning_date = now.strftime('%Y-%m-%d %H:%M:%S')
    month_year = now.strftime('%Y-%m')

    conn = sqlite3.connect('cleaning_records.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO cleanings (unit_key, display_name, cleaning_date, month_year) VALUES (?, ?, ?, ?)',
                   (unit_key, display_name, cleaning_date, month_year))
    conn.commit()

    # Count total cleanings for this unified unit key in the current month
    cursor.execute('SELECT COUNT(*), display_name FROM cleanings WHERE unit_key = ? AND month_year = ?',
                   (unit_key, month_year))
    result = cursor.fetchone()
    count = result[0]
    best_name = result[1] or unit_key
    conn.close()

    response_text = f"✅ Logged cleaning for **{best_name}**.\nTotal this month ({month_year}): **{count}/2**"
    if count >= 2:
        response_text += " 🎉 Target reached for this month!"

    await message.reply_text(response_text, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    month_year = datetime.now().strftime('%Y-%m')
    conn = sqlite3.connect('cleaning_records.db')
    cursor = conn.cursor()
    cursor.execute('SELECT display_name, COUNT(*) FROM cleanings WHERE month_year = ? GROUP BY unit_key', (month_year,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f"No cleaning records found for {month_year}.")
        return

    msg = f"📊 **Cleaning Status Summary ({month_year})**\n\n"
    for name, count in rows:
        status = "✅ Completed" if count >= 2 else f"⚠️ Incomplete ({count}/2)"
        msg += f"- **{name}**: {count} time(s) — {status}\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.TEXT, handle_message))
    app.add_handler(CommandHandler("status", status_command))

    print("Cloud Cleaning Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()