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
SCAN_THREAD = None

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

# ---------------- SCANNER LOOP (STABLE) ----------------

def run_scan():
    global SCANNING, CURRENT_URL, LOGS, TOTAL_URLS, CURRENT_INDEX

    if SCANNING:
        return

    SCANNING = True
    LOGS.append("Sürekli tarama başlatıldı...")

    while True:
        try:
            # Sitemap URL'leri çek (her tur güncellenir)
            urls = get_all_urls(TARGET_DOMAIN)

            TOTAL_URLS = len(urls)
            CURRENT_INDEX = 0

            LOGS.append(f"Sitemap bulundu: {TOTAL_URLS} URL")

            for url in urls:
                CURRENT_INDEX += 1
                CURRENT_URL = url

                LOGS.append(f"[{CURRENT_INDEX}/{TOTAL_URLS}] Taranıyor: {url}")

                # Daha önce tarandıysa atla (performans)
                if url_already_scanned(url):
                    continue

                result = scan_page(url)

                if result:
                    code, source_url = result
                    save_code(code, source_url)
                    LOGS.append(f"Yeni kod bulundu: {code}")

                mark_url_scanned(url)

                # Render timeout yememek için küçük sleep
                time.sleep(0.3)

            LOGS.append("Tur tamamlandı. 60 saniye sonra yeniden sitemap güncellenecek...")

            # Log şişmesini engelle (son 100 log)
            if len(LOGS) > 100:
                LOGS = LOGS[-100:]

            # 60 saniye bekle sonra tekrar sitemap çek (senin istediğin 5dk yerine daha canlı)
            time.sleep(60)

        except Exception as e:
            LOGS.append(f"KRITIK HATA: {str(e)}")

            if len(LOGS) > 100:
                LOGS = LOGS[-100:]

            # Hata olursa sistem durmasın
            time.sleep(10)

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/start")
def start_scan():
    global SCAN_THREAD

    # Aynı anda birden fazla thread açılmasını engeller
    if SCAN_THREAD is None or not SCAN_THREAD.is_alive():
        SCAN_THREAD = threading.Thread(target=run_scan, daemon=True)
        SCAN_THREAD.start()
        LOGS.append("Tarama thread başlatıldı (Render uyumlu daemon mod)")

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

    file_path = "codes.txt"
    with open(file_path, "w", encoding="utf-8") as f:
        for code, _ in codes:  # URL yazmaz, sadece kod
            f.write(f"{code}\n")

    return send_file(file_path, as_attachment=True)

# ---------------- STARTUP ----------------

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
