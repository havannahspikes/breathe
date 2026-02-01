#!/usr/bin/env python3
"""
breath.py — small Flask app / CLI to keep a site alive and forward pulses.

ENV vars:
- TARGET_URL     : where /send_wave will GET (default: https://who-i-am-uzh6.onrender.com/life)
- FORWARD_URL    : where inbound pulses are forwarded (default: TARGET_URL/pulse_receiver)
- FORWARD_TOKEN  : optional header value X-PULSE-TOKEN when forwarding
"""
import os
import json
from flask import Flask, request, jsonify
try:
    import requests
except Exception:
    requests = None

TARGET_URL = os.environ.get("TARGET_URL", "https://who-i-am-uzh6.onrender.com/life")
FORWARD_URL = os.environ.get("FORWARD_URL", os.environ.get("TARGET_URL", TARGET_URL).rstrip("/") + "/pulse_receiver")
FORWARD_TOKEN = os.environ.get("FORWARD_TOKEN")  # used when forwarding

app = Flask(__name__)

@app.route("/send_wave", methods=["GET"])
def send_wave():
    """Send one GET request (a small wave) to TARGET_URL."""
    if not requests:
        return jsonify({"status":"error", "error":"requests not installed"}), 500
    try:
        r = requests.get(TARGET_URL, timeout=10)
        return jsonify({"status":"ok", "target": TARGET_URL, "code": r.status_code}), 200
    except Exception as e:
        return jsonify({"status":"error", "error": str(e)}), 500

@app.route("/receive_pulse", methods=["POST", "GET"])
def receive_pulse():
    """
    Accepts an inbound pulse (json/form) and forwards it as POST to FORWARD_URL.
    Returns the forward result.
    """
    if not requests:
        return jsonify({"status":"error", "error":"requests not installed"}), 500

    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict() or {"message": "ping"}

    headers = {}
    if FORWARD_TOKEN:
        headers["X-PULSE-TOKEN"] = FORWARD_TOKEN

    try:
        r = requests.post(FORWARD_URL, json=payload, headers=headers, timeout=10)
        return jsonify({"status":"forwarded", "forward_to": FORWARD_URL, "code": r.status_code, "text": r.text[:300]}), 200
    except Exception as e:
        return jsonify({"status":"error", "error": str(e)}), 500

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Send one wave to TARGET_URL then exit")
    args = parser.parse_args()

    if args.once:
        if not requests:
            print("requests not installed")
            raise SystemExit(1)
        try:
            r = requests.get(TARGET_URL, timeout=10)
            print("sent wave", r.status_code)
            raise SystemExit(0)
        except Exception as e:
            print("error:", e)
            raise SystemExit(2)

    # default dev server (good for quick testing). Use gunicorn for production.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))
