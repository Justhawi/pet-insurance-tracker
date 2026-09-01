"""Shared-password gate for the Pet Insurance Tracker.

A cookie session with a proper login page, mirroring the retention panel, so
that "Sign out" genuinely ends the session (the old HTTP Basic gate had no
session to end — the browser simply re-sent the credentials).

Activates only when the APP_PASSWORD environment variable is set.
When APP_PASSWORD is empty/unset the site behaves exactly as before: open,
no login page, no cookie.

Left deliberately open even when the gate is on:
  /api/upload   authenticates itself with the X-Upload-Key header (the daily
                GitHub Action and fetch_live_data.py publish through it)
  /api/status   the external uptime pinger that keeps Render awake
  /static/*     logo and other public assets
"""
import hashlib
import hmac
import os
import secrets
from datetime import timedelta

from flask import redirect, request, session, Response

from cloud_server import app

_PW = os.environ.get("APP_PASSWORD", "")
_OPEN_PATHS = {"/login", "/logout", "/api/upload", "/api/status"}

# Deriving the key from the password keeps sessions alive across the frequent
# restarts of Render's free plan, and changing APP_PASSWORD signs everyone out.
app.secret_key = os.environ.get("SECRET_KEY") or hashlib.sha256(
    ("petplan-tracker::" + (_PW or secrets.token_hex(16))).encode("utf-8")
).hexdigest()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),  # https in production
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)


def _fingerprint():
    """Ties a session to the current password, so rotating it invalidates all."""
    return hashlib.sha256(("fp::" + _PW).encode("utf-8")).hexdigest()[:32]


def _safe_next(raw):
    """Only ever redirect to a path on this site."""
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return "/"
    return raw


def _signed_in():
    return session.get("auth") == _fingerprint()


@app.before_request
def _gate():
    if not _PW:
        return None
    path = request.path
    if path in _OPEN_PATHS or path.startswith("/static/"):
        return None
    if _signed_in():
        return None
    if path.startswith("/api/"):
        return Response("Authentication required.", 401, {"Content-Type": "text/plain"})
    return redirect("/login?next=" + _safe_next(path))


@app.route("/login", methods=["GET", "POST"])
def login():
    if not _PW:
        return redirect("/")
    nxt = _safe_next(request.args.get("next") or request.form.get("next"))
    if _signed_in():
        return redirect(nxt)

    error = ""
    if request.method == "POST":
        supplied = request.form.get("password", "")
        if hmac.compare_digest(supplied, _PW):
            session.permanent = True
            session["auth"] = _fingerprint()
            return redirect(nxt)
        error = "That password is not right."

    signed_out = request.args.get("signedout") == "1"
    return Response(_login_page(nxt, error, signed_out), 200 if not error else 401,
                    {"Content-Type": "text/html; charset=utf-8"})


@app.route("/logout")
def logout():
    session.clear()
    if not _PW:
        return redirect("/")
    return redirect("/login?signedout=1")


def _login_page(nxt, error, signed_out):
    note = ""
    if error:
        note = '<p class="msg bad">' + error + "</p>"
    elif signed_out:
        note = '<p class="msg ok">You have been signed out.</p>'
    return """<!DOCTYPE html>
<html lang="en" data-theme="dark" translate="no">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="google" content="notranslate">
<title>Sign in &middot; Pet Insurance Tracker &middot; Petplan</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Zilla+Slab:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --pp-blue:#0055a4; --pp-blue-dark:#00427f; --pp-cta:#c9252c; --pp-cta-dark:#a51d23;
  --surface-1:#13212e; --surface-2:#1a2c3c; --border:#23384a; --border-strong:#35506a;
  --text-primary:#eaf2f7; --text-muted:#8598a6; --brand:#82bcf1;
  --critical-bg:#2d1618; --critical-ink:#f08a8e; --good-bg:#1d2c17; --good-ink:#a5d45e;
  --slab:"Zilla Slab","American Typewriter",Rockwell,"Roboto Slab",Georgia,serif;
  --sans:Arial,"Helvetica Neue",Helvetica,sans-serif;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;min-height:100dvh;display:grid;place-items:center;padding:24px;
  background:linear-gradient(180deg,#0c1620 0%,#101f2c 100%);color:var(--text-primary);
  font-family:var(--sans);font-size:15px;line-height:1.56;-webkit-font-smoothing:antialiased}
.box{width:min(392px,100%);text-align:center}
.brand{font-family:var(--slab);font-weight:600;font-size:2.1rem;line-height:1;color:#fff;
  letter-spacing:-.01em;margin-bottom:6px}
.brand sup{font-size:.4em;top:-.9em;position:relative;font-weight:400}
.tag{font-size:.78rem;color:var(--text-muted);margin-bottom:22px}
form{background:var(--surface-1);border:1px solid var(--border);border-radius:5px;
  padding:22px 20px;box-shadow:0 1px 2px rgba(0,0,0,.35),0 3px 12px rgba(0,0,0,.28);text-align:left}
h1{font-family:var(--slab);font-weight:400;font-size:1.2rem;color:var(--brand);margin:0 0 14px}
label{display:block;font-size:.7rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
  color:var(--text-muted);margin-bottom:5px}
input{width:100%;background:#0f1c27;border:1px solid var(--border-strong);color:var(--text-primary);
  border-radius:5px;padding:10px 12px;font-size:.92rem;font-family:var(--sans);outline:none}
input:focus{border-color:var(--brand);box-shadow:0 0 0 3px rgba(130,188,241,.18)}
button{margin-top:14px;width:100%;display:inline-flex;align-items:center;justify-content:center;
  font-family:var(--slab);font-size:.98rem;padding:11px 20px;border-radius:5px;border:1px solid var(--pp-cta);
  background:var(--pp-cta);color:#fff;cursor:pointer;transition:background .14s}
button:hover{background:var(--pp-cta-dark)}
.msg{margin:0 0 12px;padding:9px 12px;border-radius:5px;font-size:.8rem}
.msg.bad{background:var(--critical-bg);color:var(--critical-ink)}
.msg.ok{background:var(--good-bg);color:var(--good-ink)}
.foot{margin-top:16px;font-size:.72rem;color:var(--text-muted);line-height:1.5}
</style>
</head>
<body>
  <div class="box">
    <div class="brand">Petplan<sup>&reg;</sup></div>
    <div class="tag">Pet Insurance Live Tracker</div>
    <form method="post" action="/login" autocomplete="off">
      <h1>Sign in</h1>
      __NOTE__
      <input type="hidden" name="next" value="__NEXT__">
      <label for="password">Shared password</label>
      <input type="password" id="password" name="password" autocomplete="current-password" autofocus required>
      <button type="submit">Sign in</button>
    </form>
    <p class="foot">Internal tool. It holds only public reputation data about
      insurance companies &mdash; no customer names, policies or personal data.</p>
  </div>
</body>
</html>""".replace("__NOTE__", note).replace(
        "__NEXT__", nxt.replace('"', "&quot;")
    )


# Procfile runs: gunicorn auth_gate:app
application = app
