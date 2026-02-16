from flask import Flask, render_template, jsonify, send_file
import psycopg2
import os
import threading
import time
from datetime import datetime
from scanner import scan_domain

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
TARGET_DOMAIN = "https://vkmspor.com"

SCANNING = False
CURRENT_URL = ""
LOGS = []

# ---------------- DATABASE ----------------

def get_connection():
    return psycopg2.connect(DATABASE_URL)

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
    try:
        cur.execute("INSERT INTO scanned_urls (url, scanned_at) VALUES (%s, %s)",
                    (url, datetime.utcnow()))
        conn.commit()
    except:
        pass
    conn.close()

def save_code(code, url):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO codes (code, source_url, created_at)
            VALUES (%s, %s, %s)
        """, (code, url, datetime.utcnow()))
        conn.commit()
    except:
        pass
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

def scanner_loop():
    global SCANNING, CURRENT_URL

    while True:
        SCANNING = True
        CURRENT_URL = TARGET_DOMAIN
        LOGS.append(f"Tarama başladı: {TARGET_DOMAIN}")

        try:
            if not url_already_scanned(TARGET_DOMAIN):
                results = scan_domain(TARGET_DOMAIN)

                for code, url in results:
                    save_code(code, url)
                    LOGS.append(f"Yeni kod: {code} ({url})")

                mark_url_scanned(TARGET_DOMAIN)
                LOGS.append("URL işaretlendi (tekrar taranmayacak)")
            else:
                LOGS.append("Bu URL daha önce tarandı, atlandı.")

        except Exception as e:
            LOGS.append(f"Hata: {e}")

        SCANNING = False
        time.sleep(300)

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    return render_template("index.html")

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
        "logs": LOGS[-20:]
    })

@app.route("/download")
def download():
    codes = get_all_codes()
    with open("codes.txt", "w") as f:
        for code, url in codes:
            f.write(f"{code} - {url}\n")

    return send_file("codes.txt", as_attachment=True)

# ---------------- START ----------------

if __name__ == "__main__":
    init_db()
    threading.Thread(target=scanner_loop, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
