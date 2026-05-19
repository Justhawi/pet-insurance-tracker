#!/usr/bin/env python3
"""
Pet Insurance Tracker — Cloud Server (Render.com)
Serves the dashboard 24/7.
Data is pushed from the local fetch script after each run.
"""
import json, os, re
from datetime import datetime
from flask import Flask, jsonify, request, abort

app    = Flask(__name__)
HERE   = os.path.dirname(os.path.abspath(__file__))
DATA   = os.path.join(HERE, "companies_data.json")
HTML   = os.path.join(HERE, "pet_insurance_tracker.html")

UPLOAD_KEY = os.environ.get("UPLOAD_KEY", "change-me-123")

def load():
    if os.path.exists(DATA):
        try:
            with open(DATA, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save(results):
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    if os.path.exists(HTML):
        with open(HTML, "r", encoding="utf-8") as f:
            html = f.read()
        new_js = "const SEED_DATA = " + json.dumps(results, ensure_ascii=False, separators=(",",":")) + ";"
        html = re.sub(r"const SEED_DATA\s*=\s*\[.*?\];", new_js, html, flags=re.DOTALL)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        html = re.sub(r"(getElementById\('lastUpdated'\)\.textContent\s*=\s*')[^']*(')", f"\\1Updated: {stamp} (live)\\2", html)
        with open(HTML, "w", encoding="utf-8") as f:
            f.write(html)

@app.route("/")
def index():
    if os.path.exists(HTML):
        with open(HTML, encoding="utf-8") as f:
            return f.read()
    return "<h2>No data yet — run the fetch script on your PC first.</h2>"

@app.route("/api/data")
def api_data():
    country = request.args.get("country")
    data = load()
    if country:
        data = [c for c in data if c.get("country","").lower() == country.lower()]
    return jsonify(data)

@app.route("/api/status")
def api_status():
    data = load()
    return jsonify({"companies": len(data), "last_fetch": data[0].get("date") if data else "never", "server": "cloud"})

@app.route("/api/upload", methods=["POST"])
def api_upload():
    key = request.headers.get("X-Upload-Key","") or request.args.get("key","")
    if key != UPLOAD_KEY:
        abort(401)
    try:
        body = request.get_json(force=True)
        if not isinstance(body, list):
            return jsonify({"error": "Expected a JSON array"}), 400
        save(body)
        return jsonify({"ok": True, "companies": len(body), "updated": datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
