import os
import logging
import re
import sqlite3
from datetime import datetime
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.environ.get("TOKEN")

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Cleaning Bot is active and running!")

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()

web_thread = Thread(target=run_web_server, daemon=True)
web_thread.start()

def init_db():
    conn = sqlite3.connect('cleaning_records.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cleanings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_number TEXT,
            cleaning_date TEXT,
            month_year TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    text = message.caption or message.text
    if not text:
        return

    match = re.search(r'unit\s*([a-zA-Z0-9-]+)', text, re.IGNORECASE)
    if not match:
        return 

    unit_number = match.group(1).upper()
    now = datetime.now()
    cleaning_date = now.strftime('%Y-%m-%d %H:%M:%S')
    month_year = now.strftime('%Y-%m')

    conn = sqlite3.connect('cleaning_records.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO cleanings (unit_number, cleaning_date, month_year) VALUES (?, ?, ?)',
                   (unit_number, cleaning_date, month_year))
    conn.commit()

    cursor.execute('SELECT COUNT(*) FROM cleanings WHERE unit_number = ? AND month_year = ?',
                   (unit_number, month_year))
    count = cursor.fetchone()[0]
    conn.close()

    response_text = f"✅ Logged cleaning for **Unit {unit_number}**.\nTotal this month ({month_year}): **{count}/2**"
    if count >= 2:
        response_text += " 🎉 Target reached for this month!"

    await message.reply_text(response_text, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    month_year = datetime.now().strftime('%Y-%m')
    conn = sqlite3.connect('cleaning_records.db')
    cursor = conn.cursor()
    cursor.execute('SELECT unit_number, COUNT(*) FROM cleanings WHERE month_year = ? GROUP BY unit_number', (month_year,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f"No cleaning records found for {month_year}.")
        return

    msg = f"📊 **Cleaning Status Summary ({month_year})**\n\n"
    for unit, count in rows:
        status = "✅ Completed" if count >= 2 else f"⚠️ Incomplete ({count}/2)"
        msg += f"- **Unit {unit}**: {count} time(s) — {status}\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.TEXT, handle_message))
    app.add_handler(CommandHandler("status", status_command))

    print("Cloud Cleaning Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()