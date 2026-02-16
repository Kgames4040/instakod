from flask import Flask, render_template, jsonify, send_file
import psycopg2
import os
import threading
from datetime import datetime
from scanner import get_all_urls, scan_page

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
TARGET_DOMAIN = "https://vkmspor.com"

SCANNING = False
CURRENT_URL = ""
LOGS = []

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

# ---------------- SCANNER ----------------

def run_scan():
    global SCANNING, CURRENT_URL, LOGS

    if SCANNING:
        return

    SCANNING = True
    LOGS.append("Tarama başlatıldı...")

    try:
        urls = get_all_urls(TARGET_DOMAIN)

        for url in urls:

            CURRENT_URL = url
            LOGS.append(f"Taranıyor: {url}")

            if url_already_scanned(url):
                LOGS.append("Atlandı (zaten taranmış)")
                continue

            result = scan_page(url)

            if result:
                code, source_url = result
                save_code(code, source_url)
                LOGS.append(f"Yeni kod bulundu: {code}")

            mark_url_scanned(url)

        LOGS.append("Tarama tamamlandı.")

    except Exception as e:
        LOGS.append(f"Hata: {e}")

    SCANNING = False
    LOGS = LOGS[-100:]  # Son 100 log tutulur

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
        "logs": LOGS
    })

@app.route("/download")
def download():
    codes = get_all_codes()

    with open("codes.txt", "w") as f:
        for code, url in codes:
            f.write(f"{code} - {url}\n")

    return send_file("codes.txt", as_attachment=True)

# ---------------- START ----------------

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
