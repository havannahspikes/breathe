#!/usr/bin/env python3
"""
breathe.py — small Flask app + background auto-pinger.

Behavior:
 - GET  /             -> status JSON
 - GET  /send_wave    -> send a single GET to TARGET_URL
 - POST /receive_pulse-> forward the incoming JSON/form to FORWARD_URL (with optional X-PULSE-TOKEN)
 - Background thread (daemon) optionally sends POST pulses to FORWARD_URL at random intervals
   between MIN_INTERVAL and MAX_INTERVAL seconds (defaults: 15..49)

ENV vars:
 - TARGET_URL       : where /send_wave will GET (default: https://who-i-am-uzh6.onrender.com/life)
 - FORWARD_URL      : where inbound pulses are forwarded (default: TARGET_URL.rstrip('/') + '/pulse_receiver')
 - FORWARD_TOKEN    : optional header value X-PULSE-TOKEN when forwarding
 - AUTO_PING        : "true"/"1"/"yes" to enable background pinger (default: true)
 - MIN_INTERVAL     : min seconds for random interval (default: 15)
 - MAX_INTERVAL     : max seconds for random interval (default: 49)
"""
import os
import time
import random
import threading
import json
import sys
from flask import Flask, request, jsonify

# optional dependency — if not installed the endpoints will still run but return errors for network ops
try:
    import requests
except Exception:
    requests = None

# configuration (defaults tuned to your request)
TARGET_URL = os.environ.get("TARGET_URL", "https://who-i-am-uzh6.onrender.com/life")
FORWARD_URL = os.environ.get("FORWARD_URL", (os.environ.get("TARGET_URL") or TARGET_URL).rstrip("/") + "/pulse_receiver")
FORWARD_TOKEN = os.environ.get("FORWARD_TOKEN")  # optional X-PULSE-TOKEN when forwarding

AUTO_PING = os.environ.get("AUTO_PING", "true").lower() in ("1", "true", "yes")
try:
    MIN_INTERVAL = float(os.environ.get("MIN_INTERVAL", "15"))
    MAX_INTERVAL = float(os.environ.get("MAX_INTERVAL", "49"))
except Exception:
    MIN_INTERVAL = 15.0
    MAX_INTERVAL = 49.0

# sane fallback if envs are nonsense
if MIN_INTERVAL <= 0 or MAX_INTERVAL <= 0 or MIN_INTERVAL > MAX_INTERVAL:
    MIN_INTERVAL = 15.0
    MAX_INTERVAL = 49.0

app = Flask(__name__)
_start_time = time.time()
session = requests.Session() if requests else None

def _log(*a, **k):
    print(*a, **k)
    sys.stdout.flush()

@app.route("/")
def root():
    return jsonify({
        "status": "alive",
        "uptime_seconds": int(time.time() - _start_time),
        "auto_ping": AUTO_PING,
        "min_interval": MIN_INTERVAL,
        "max_interval": MAX_INTERVAL,
        "target": TARGET_URL,
        "forward_to": FORWARD_URL
    })

@app.route("/send_wave", methods=["GET"])
def send_wave():
    """Send one GET request (a small wave) to TARGET_URL."""
    if not session:
        return jsonify({"status":"error", "error":"requests not installed"}), 500
    try:
        r = session.get(TARGET_URL, timeout=10)
        return jsonify({"status":"ok", "target": TARGET_URL, "code": r.status_code}), 200
    except Exception as e:
        return jsonify({"status":"error", "error": str(e)}), 500

@app.route("/receive_pulse", methods=["POST", "GET"])
def receive_pulse():
    """
    Accept inbound pulse and forward it to FORWARD_URL as a POST (JSON).
    Returns forward result summary.
    """
    if not session:
        return jsonify({"status":"error", "error":"requests not installed"}), 500

    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() or {"message": "ping"}

    headers = {}
    if FORWARD_TOKEN:
        headers["X-PULSE-TOKEN"] = FORWARD_TOKEN

    try:
        r = session.post(FORWARD_URL, json=payload, headers=headers, timeout=10)
        return jsonify({
            "status":"forwarded",
            "forward_to": FORWARD_URL,
            "code": r.status_code,
            "text_snippet": (r.text[:300] if r.text else "")
        }), 200
    except Exception as e:
        return jsonify({"status":"error", "error": str(e)}), 500

def auto_ping_loop():
    """Daemon loop — sends POST to FORWARD_URL at random intervals between MIN_INTERVAL and MAX_INTERVAL."""
    if not session:
        _log("auto_ping: requests not available; auto pinger disabled")
        return
    _log(f"auto_ping: starting loop -> forwarding to {FORWARD_URL} every {MIN_INTERVAL}-{MAX_INTERVAL}s (random)")
    while True:
        wait = random.uniform(MIN_INTERVAL, MAX_INTERVAL)
        _log(f"auto_ping: sleeping {wait:.2f}s")
        time.sleep(wait)
        payload = {"source": "breathe", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        headers = {}
        if FORWARD_TOKEN:
            headers["X-PULSE-TOKEN"] = FORWARD_TOKEN
        try:
            r = session.post(FORWARD_URL, json=payload, headers=headers, timeout=10)
            _log(f"auto_ping: POST {FORWARD_URL} -> {r.status_code}")
        except Exception as e:
            _log(f"auto_ping: error posting to {FORWARD_URL}: {e}")

# start the background auto-pinger if enabled
if AUTO_PING:
    t = threading.Thread(target=auto_ping_loop, name="auto_ping", daemon=True)
    t.start()
else:
    _log("auto_ping: disabled (set AUTO_PING=true to enable)")

# CLI single-run helper
def send_once_and_exit():
    if not requests:
        print("requests not installed", file=sys.stderr)
        raise SystemExit(1)
    try:
        r = session.get(TARGET_URL, timeout=10)
        print("sent wave", r.status_code)
        raise SystemExit(0)
    except Exception as e:
        print("error:", e, file=sys.stderr)
        raise SystemExit(2)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Send one wave to TARGET_URL then exit")
    args = parser.parse_args()
    if args.once:
        send_once_and_exit()
    # dev server for local testing — use gunicorn in production
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))
