"""SEO Lens inside the Pet Insurance Tracker.

Same screens and the same API paths the stand-alone SEO Lens had, so its page
works unchanged:

  GET /seo                the SEO Lens app (audit, compare, guide, assistant)
  GET /api/audit?url=     on-page audit + Googlebot cloaking check + robots.txt
  GET /api/cwv?url=       Core Web Vitals from Google PageSpeed Insights
  GET /api/drafts         blog drafts awaiting review (nothing is published)
  GET /api/dupe?t=        duplicate check of a title against the live blog

Everything sits behind the tracker's login (auth_gate.py).
"""
import json
import os
import re
import unicodedata

from flask import Blueprint, Response, request

import seo_audit

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE_FILE = os.path.join(HERE, "seo_lens.html")
DRAFTS_FILE = os.path.join(HERE, "seo_drafts.json")

bp = Blueprint("seo_lens", __name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def _allow_private():
    return bool(os.environ.get("ALLOW_PRIVATE"))


def send(obj, status=200):
    # json.dumps keeps key order (jsonify would sort it, and the page lists
    # some objects in the order the server sends them).
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return Response(
        body,
        status,
        {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
         **SECURITY_HEADERS},
    )


@bp.route("/seo")
@bp.route("/seo/")
def seo_page():
    with open(PAGE_FILE, encoding="utf-8") as f:
        html = f.read()
    if os.environ.get("APP_PASSWORD"):
        # Tells the page a session exists, so it shows the sign-out item.
        html = html.replace('data-auth="0"', 'data-auth="1"', 1)
    return Response(
        html, 200, {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
                    **SECURITY_HEADERS}
    )


@bp.route("/api/audit")
def api_audit():
    target = request.args.get("url")
    if not target:
        return send({"ok": False, "error": "Add a ?url= parameter."}, 400)
    try:
        parsed = seo_audit.parse_target(target)
    except ValueError:
        return send({"ok": False, "error": "That doesn't look like a valid URL."}, 400)
    host = re.sub(r"^\[|\]$", "", seo_audit.urlsplit(parsed).hostname or "")
    if seo_audit.is_private_host(host) and not _allow_private():
        return send({"ok": False, "error": "Private and local addresses cannot be audited."}, 400)
    try:
        result = seo_audit.run_audit(parsed, allow_private=_allow_private())
        return send(result, 200 if result.get("ok") else 400)
    except Exception as e:  # noqa: BLE001
        return send({"ok": False, "error": str(e)}, 500)


@bp.route("/api/cwv")
def api_cwv():
    target = request.args.get("url")
    if not target:
        return send({"ok": False, "error": "Add a ?url= parameter."}, 400)
    try:
        return send(seo_audit.fetch_core_web_vitals(target))
    except Exception as e:  # noqa: BLE001
        return send({"ok": False, "error": str(e)}, 500)


@bp.route("/api/drafts")
def api_drafts():
    with open(DRAFTS_FILE, encoding="utf-8") as f:
        d = json.load(f)
    return send({"ok": True, "cta": d["cta"], "drafts": d["drafts"]})


_DUPE_STOP = {"para", "como", "que", "los", "las", "del", "con", "una", "por",
              "the", "and", "your", "what", "how"}


def _dupe_words(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = re.sub("[̀-ͯ]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    out = {}
    for w in re.split(seo_audit.S + "+", s):
        if len(w) > 3 and w not in _DUPE_STOP:
            out[w] = True
    return out


@bp.route("/api/dupe")
def api_dupe():
    """Duplicate check against the live blog, so it never relies on a stale list."""
    q = seo_audit.trim(request.args.get("t") or "")
    if not q:
        return send({"ok": False, "error": "Add a ?t= parameter."}, 400)
    a = _dupe_words(q)
    try:
        r = seo_audit.http_get(
            "https://petplan.es/wp-json/wp/v2/posts?per_page=10&_fields=slug,title&search="
            + seo_audit.quote(q, safe="-_.!~*'()"),
            {"user-agent": "SEO Lens duplicate check"},
            allow_private=True,
        )
        if not r.ok:
            return send({"ok": False, "error": "WordPress responded " + str(r.status)}, 502)
        try:
            total = int(float(r.headers.get("x-wp-total") or 0))
        except ValueError:
            total = 0
        matches = []
        for p in r.json():
            t = re.sub(r"<[^>]*>", "", str(((p.get("title") or {}).get("rendered")) or ""))
            b = _dupe_words(t)
            hit = sum(1 for w in a if w in b)
            union = len(set(a) | set(b)) or 1
            score = seo_audit.js_number(float(seo_audit.to_fixed(hit / union, 2)))
            matches.append({"title": t, "slug": p.get("slug"), "score": score})
        matches.sort(key=lambda m: -m["score"])
        return send({"ok": True, "total": total, "matches": matches})
    except Exception as e:  # noqa: BLE001
        return send({"ok": False, "error": seo_audit._err(e)}, 500)
