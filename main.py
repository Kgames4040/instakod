from flask import Flask, render_template, jsonify, send_file
import psycopg2
import os
import threading
import time
from datetime import datetime
from scanner import get_all_urls, scan_page

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
TARGET_DOMAIN = "https://vkmspor.com"

SCANNING = False
CURRENT_URL = ""
LOGS = []
TOTAL_URLS = 0
CURRENT_INDEX = 0

# ---------------- DATABASE ----------------

def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE,
            source_url TEXT,
            created_at TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS scanned_urls (
            id SERIAL PRIMARY KEY,
            url TEXT UNIQUE,
            scanned_at TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

def url_already_scanned(url):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM scanned_urls WHERE url=%s", (url,))
    result = cur.fetchone()
    conn.close()
    return result is not None

def mark_url_scanned(url):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO scanned_urls (url, scanned_at)
        VALUES (%s, %s)
        ON CONFLICT (url) DO NOTHING
    """, (url, datetime.utcnow()))
    conn.commit()
    conn.close()

def save_code(code, url):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO codes (code, source_url, created_at)
        VALUES (%s, %s, %s)
        ON CONFLICT (code) DO NOTHING
    """, (code, url, datetime.utcnow()))
    conn.commit()
    conn.close()

def get_all_codes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT code, source_url
        FROM codes
        ORDER BY id DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

# ---------------- SCANNER LOOP ----------------

def run_scan():
    global SCANNING, CURRENT_URL, LOGS, TOTAL_URLS, CURRENT_INDEX

    if SCANNING:
        return

    SCANNING = True
    LOGS.append("Sürekli tarama başlatıldı...")

    while SCANNING:
        try:
            urls = get_all_urls(TARGET_DOMAIN)
            TOTAL_URLS = len(urls)
            CURRENT_INDEX = 0

            for url in urls:
                CURRENT_INDEX += 1
                CURRENT_URL = url

                LOGS.append(f"[{CURRENT_INDEX}/{TOTAL_URLS}] Taranıyor: {url}")

                if not url_already_scanned(url):

                    result = scan_page(url)

                    if result:
                        code, source_url = result
                        save_code(code, source_url)
                        LOGS.append(f"Yeni kod: {code}")

                    mark_url_scanned(url)

                time.sleep(0.5)

            LOGS.append("Tur tamamlandı. 60 saniye bekleniyor...")
            LOGS = LOGS[-100:]
            time.sleep(60)

        except Exception as e:
            LOGS.append(f"Hata: {e}")
            LOGS = LOGS[-100:]
            time.sleep(10)

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start")
def start_scan():
    threading.Thread(target=run_scan).start()
    return jsonify({"status": "started"})

@app.route("/status")
def status():
    codes = get_all_codes()
    last = codes[0] if codes else ("Yok", "Yok")

    return jsonify({
        "scanning": SCANNING,
        "current_url": CURRENT_URL,
        "last_code": last[0],
        "last_url": last[1],
        "total": len(codes),
        "codes": codes,
        "logs": LOGS,
        "total_urls": TOTAL_URLS,
        "current_index": CURRENT_INDEX
    })

@app.route("/download")
def download():
    codes = get_all_codes()
    with open("codes.txt", "w") as f:
        for code, url in codes:
            f.write(f"{code}\n")
    return send_file("codes.txt", as_attachment=True)

# ---------------- START ----------------

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
