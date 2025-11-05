#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

from flask import Flask, request, jsonify, abort
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
import requests
import jwt
from functools import wraps

# ---------- CONFIG ----------
DB_CONFIG = {
    "host": "<DB_HOST>",
    "user": "<DB_USER>",
    "password": "<DB_PASSWORD>",
    "database": "<DB_NAME>",
    "connection_timeout": 10,
    "autocommit": True
}

SECRET_KEY = "change_this_random_secret_in_production"
CHECK_INTERVAL_SECONDS = 60
REQUEST_TIMEOUT = 10


app = Flask(__name__)
CORS(app)

# ---------- JWT helpers ----------
def create_token(username):
    payload = {"username": username, "exp": datetime.utcnow() + timedelta(hours=4)}
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def decode_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload["username"]
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error":"Hiányzó token"}), 401
        token = auth_header.split(" ")[1]
        username = decode_token(token)
        if not username:
            return jsonify({"error":"Érvénytelen vagy lejárt token"}), 401
        request.user = username
        return f(*args, **kwargs)
    return decorated

# ---------- DB helpers ----------
def get_db_conn():
    return mysql.connector.connect(**DB_CONFIG)

def ensure_schema():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("CREATE DATABASE IF NOT EXISTS uptime_monitor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cur.execute("USE uptime_monitor;")
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );""")
    cur.execute("""CREATE TABLE IF NOT EXISTS sites (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    url VARCHAR(2048) NOT NULL,
                    last_status TINYINT(1) DEFAULT 0,
                    last_checked TIMESTAMP NULL,
                    down_since TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );""")
    cur.execute("""CREATE TABLE IF NOT EXISTS checks (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    site_id INT NOT NULL,
                    status TINYINT(1) NOT NULL,
                    http_code INT NULL,
                    response_time_ms INT NULL,
                    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (site_id) REFERENCES sites(id) ON DELETE CASCADE
                );""")
    cur.close()
    conn.close()

def ensure_admin_user():
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("USE uptime_monitor;")
    cur.execute("SELECT * FROM users WHERE username = %s", ("admin",))
    row = cur.fetchone()
    if not row:
        pw_hash = generate_password_hash("PASSWORD1234")
        cur.execute("INSERT INTO users (username, password_hash) VALUES (%s,%s)", ("admin", pw_hash))
        print("[setup] Created admin user with username 'admin' and provided password.")
    cur.close()
    conn.close()

# ---------- Routes ----------
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"error":"Hiányzó adatok"}), 400
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("USE uptime_monitor;")
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if user and check_password_hash(user["password_hash"], password):
        token = create_token(username)
        return jsonify({"token": token})
    return jsonify({"error":"Hibás felhasználónév vagy jelszó"}), 401

@app.route("/api/sites", methods=["GET","POST"])
@token_required
def api_sites():
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("USE uptime_monitor;")
    if request.method == "GET":
        cur.execute("SELECT * FROM sites ORDER BY id DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        for r in rows:
            if r["last_checked"]:
                r["last_checked"] = r["last_checked"].isoformat(sep=" ", timespec="seconds")
            if r["down_since"]:
                r["down_since"] = r["down_since"].isoformat(sep=" ", timespec="seconds")
        return jsonify(rows)
    else:
        data = request.json or {}
        name = (data.get("name") or "").strip()
        url = (data.get("url") or "").strip()
        if not name or not url:
            return jsonify({"error":"Kérlek add meg az oldal nevét és URL-t"}), 400
        if not urlparse(url).scheme:
            url = "http://" + url
        cur.execute("INSERT INTO sites (name, url) VALUES (%s,%s)", (name, url))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok":True})

@app.route("/api/sites/<int:site_id>", methods=["DELETE"])
@token_required
def api_site_delete(site_id):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("USE uptime_monitor;")
    cur.execute("DELETE FROM sites WHERE id = %s", (site_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok":True})

@app.route("/api/status", methods=["GET"])
@token_required
def api_status():
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("USE uptime_monitor;")
    cur.execute("SELECT COUNT(*) AS total FROM sites")
    total = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) AS down FROM sites WHERE last_status = 0 OR last_status IS NULL")
    down = cur.fetchone()["down"]
    cur.close()
    conn.close()
    return jsonify({"total": total, "down": down})

# ---------- Uptime checker ----------
def check_site(site):
    site_id = site["id"]
    url = site["url"]
    try:
        ts_start = time.time()
        r = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        elapsed = int((time.time() - ts_start) * 1000)
        status = 1 if r.status_code < 400 else 0
        http_code = r.status_code
    except Exception:
        status = 0
        http_code = None
        elapsed = None

    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("USE uptime_monitor;")
    cur.execute("SELECT last_status, down_since FROM sites WHERE id = %s", (site_id,))
    prev = cur.fetchone()
    now = datetime.utcnow()
    down_since = prev["down_since"]
    if status == 1:
        down_since = None
    else:
        if prev["last_status"] == 1 or prev["last_status"] is None:
            down_since = now
    cur.execute("""UPDATE sites 
                   SET last_status = %s, last_checked = %s, down_since = %s
                   WHERE id = %s""", (status, now, down_since, site_id))
    cur.execute("INSERT INTO checks (site_id, status, http_code, response_time_ms) VALUES (%s,%s,%s,%s)",
                (site_id, status, http_code, elapsed))
    conn.commit()
    cur.close()
    conn.close()

def worker_loop():
    while True:
        try:
            conn = get_db_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute("USE uptime_monitor;")
            cur.execute("SELECT id, name, url FROM sites")
            sites = cur.fetchall()
            cur.close()
            conn.close()
            for s in sites:
                try:
                    check_site(s)
                except Exception as e:
                    print("[checker] Error checking", s.get("url"), e)
        except Exception as e:
            print("[checker] DB or other error:", e)
        time.sleep(CHECK_INTERVAL_SECONDS)

def start_worker_in_background():
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()

# ---------- Startup ----------
if __name__ == "__main__":
    print("[startup] Ensuring DB schema...")
    ensure_schema()
    ensure_admin_user()
    print("[startup] Starting background checker thread (interval:", CHECK_INTERVAL_SECONDS, "s )")
    start_worker_in_background()
    app.run(host="0.0.0.0", port=5000)
