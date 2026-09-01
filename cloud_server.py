#!/usr/bin/env python3
"""
Pet Insurance Tracker - Cloud Server (Render.com)
Serves the dashboard 24/7.
Data is pushed from the local fetch script after each run.
"""
import json, os, re, time, threading
from datetime import datetime
from flask import Flask, jsonify, request, abort, Response

app    = Flask(__name__)
HERE   = os.path.dirname(os.path.abspath(__file__))
DATA   = os.path.join(HERE, "companies_data.json")
HTML   = os.path.join(HERE, "pet_insurance_tracker.html")

# Secret key -- set this as an environment variable on Render
UPLOAD_KEY = os.environ.get("UPLOAD_KEY", "")

# -- helpers ----------------------------------------------------------
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
    # Also bake into HTML so offline view works too
    if os.path.exists(HTML):
        with open(HTML, encoding="utf-8", errors="replace") as f:
            html = f.read()
        new_js = "const SEED_DATA = " + json.dumps(results, ensure_ascii=False, separators=(",",":")) + ";"
        html   = re.sub(r"const SEED_DATA\s*=\s*\[.*?\];", new_js, html, flags=re.DOTALL)
        stamp  = datetime.now().strftime("%Y-%m-%d %H:%M")
        html   = re.sub(
            r"(getElementById\('lastUpdated'\)\.textContent\s*=\s*')[^']*(')",
            f"\\1Updated: {stamp} (live)\\2", html)
        with open(HTML, "w", encoding="utf-8") as f:
            f.write(html)

# -- routes -----------------------------------------------------------
@app.route("/")
def index():
    if os.path.exists(HTML):
        # Read as binary to handle any encoding in the file
        with open(HTML, "rb") as f:
            content = f.read()
        resp = Response(content, mimetype="text/html; charset=utf-8")
        # The dashboard is one big HTML file that changes with every deploy.
        # Without this the browser keeps serving the copy it already has, so a
        # deploy looks like it did nothing until someone hard-refreshes.
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp
    return "<h2>No data yet - run the fetch script on your PC first.</h2>"

@app.route("/api/data")
def api_data():
    country = request.args.get("country")
    data    = load()
    if country:
        data = [c for c in data if c.get("country","").lower() == country.lower()]
    return jsonify(data)

@app.route("/api/status")
def api_status():
    data = load()
    return jsonify({
        "companies": len(data),
        "last_fetch": data[0].get("date") if data else "never",
        "server": "cloud"
    })

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    Called automatically by the local fetch script after each run.
    Requires the X-Upload-Key header to match UPLOAD_KEY.
    """
    key = request.headers.get("X-Upload-Key","") or request.args.get("key","")
    if not UPLOAD_KEY or key != UPLOAD_KEY:
        abort(401)
    try:
        body = request.get_json(force=True)
        if not isinstance(body, list):
            return jsonify({"error": "Expected a JSON array"}), 400
        save(body)
        return jsonify({"ok": True, "companies": len(body),
                        "updated": datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -- live refresh (triggered by the dashboard's Refresh button) -------
# Runs the fetch in a background thread so the HTTP request returns instantly.
_refresh = {"running": False, "started": None, "finished": None,
            "message": "idle", "count": 0, "error": None,
            "mode": None, "tp_live": 0, "tp_kept": 0,
            "g_live": 0, "g_kept": 0}
_MIN_INTERVAL = 60   # seconds; ignore refreshes fired closer than this (cost guard)

def _browser_available():
    """True only when a real Playwright Chromium is installed (i.e. on the PC).
    Render's build can't install Chromium, so this is False there and we fall
    back to the HTTP method. On the PC it's True, so the Refresh button does a
    full, reliable browser fetch of Trustpilot + Google (not blocked)."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path
            return bool(path and os.path.exists(path))
    except Exception:
        return False

def _do_refresh():
    use_browser = _browser_available()
    # Detect whether a Google Places API key is configured on this host.
    try:
        import fetch_live_data as _fld_probe
        has_google = bool(getattr(_fld_probe, "GOOGLE_API_KEY", "") or
                          os.environ.get("GOOGLE_PLACES_API_KEY", ""))
    except Exception:
        has_google = bool(os.environ.get("GOOGLE_PLACES_API_KEY", ""))

    # Option 1 deployment: no browser AND no Google key on the server. There is no
    # live source here — the data is published from the office PC. Don't run a
    # pointless fetch; just tell the viewer the data is the latest published copy.
    if (not use_browser) and (not has_google):
        data = load()
        tp_date = ""
        for c in data:
            if c.get("tpDate"):
                tp_date = c["tpDate"]; break
        _refresh.update(running=False, error=None, mode="published",
                        count=len(data), tp_date=tp_date,
                        message="This site shows the latest data published from the office PC.",
                        finished=datetime.now().isoformat())
        return

    # On the PC (browser available) we fetch BOTH sources live.
    # On the cloud host WITH a Google key we refresh GOOGLE live via the Places API
    # and keep the existing Trustpilot snapshot — Trustpilot can't be scraped
    # reliably from a data-center, so we never overwrite good data with a block.
    google_only = (not use_browser)
    mode = "browser" if use_browser else "google_only"
    _refresh.update(running=True, error=None, mode=mode,
                    tp_live=0, tp_kept=0, g_live=0, g_kept=0,
                    message=("Starting full browser fetch (Trustpilot + Google)…"
                             if use_browser else
                             "Refreshing Google live (Places API); keeping Trustpilot snapshot…"))
    try:
        import fetch_live_data as fld
        def cb(line):
            _refresh["message"] = str(line)[-160:]
        results = fld.run_fetch(progress_cb=cb, discover=use_browser,
                                use_browser=use_browser, google_only=google_only)
        # run_fetch already wrote companies_data.json + baked the HTML in this folder
        tp_live = sum(1 for c in results if c.get("tpStatus") == "ok" and (c.get("tpScore") or 0) > 0)
        g_live  = sum(1 for c in results if c.get("gStatus") == "ok")
        g_kept  = sum(1 for c in results if c.get("gStatus") == "error")
        tp_date = ""
        for c in results:
            if c.get("tpDate"):
                tp_date = c["tpDate"]; break
        if use_browser:
            msg = f"Done — Trustpilot {tp_live} live, Google {g_live} live"
        else:
            msg = f"Done — Google {g_live} refreshed live; Trustpilot kept (as of {tp_date or 'last fetch'})"
        _refresh.update(count=len(results), tp_live=tp_live, tp_kept=0,
                        g_live=g_live, g_kept=g_kept, tp_date=tp_date, message=msg)
    except Exception as e:
        _refresh.update(error=str(e), message=f"Error: {e}")
    finally:
        _refresh.update(running=False, finished=datetime.now().isoformat())

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Kick off a live re-fetch of Trustpilot + Google Maps in the background."""
    if _refresh["running"]:
        return jsonify({"ok": True, "already_running": True, "message": _refresh["message"]})
    # cost guard: don't allow rapid repeated refreshes
    if _refresh["finished"]:
        try:
            last = datetime.fromisoformat(_refresh["finished"])
            if (datetime.now() - last).total_seconds() < _MIN_INTERVAL:
                return jsonify({"ok": True, "throttled": True,
                                "message": "Just refreshed — please wait a moment."})
        except Exception:
            pass
    # Mark it running *before* returning: the dashboard polls immediately, and if
    # the worker thread has not started yet it used to read running=False with no
    # finished timestamp and report a bogus "done" with a 1970 date.
    _refresh.update(running=True, finished=None, error=None,
                    started=datetime.now().isoformat(), message="Queued…")
    threading.Thread(target=_do_refresh, daemon=True).start()
    return jsonify({"ok": True, "started": True})

@app.route("/api/refresh-status")
def api_refresh_status():
    return jsonify(_refresh)

# -- entry point ------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
