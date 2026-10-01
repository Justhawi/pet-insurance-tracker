"""SEO Lens audit engine, ported from seo-lens/audit.js.

Everything here works on raw HTML strings, exactly like the JavaScript
original, so a page audited here gives the same findings as SEO Lens did.
JavaScript details that change results are reproduced on purpose:

  * string lengths are counted in UTF-16 units (JS ``.length``)
  * ``\\s`` and ``.trim()`` use the JavaScript whitespace set
  * ``toFixed`` rounds half-up on the exact binary value
  * object key order follows JS rules (integer-like keys first)
  * response bodies are always decoded as UTF-8 (``Response.text()``)

No third-party packages: only the standard library.
"""
import gzip
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.request
import zlib
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

GOOGLEBOT_UA = (
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; "
    "+http://www.google.com/bot.html) Chrome/120.0.0.0 Safari/537.36"
)
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# JavaScript's \s, which differs slightly from Python's.
_WS = "\t\n\x0b\x0c\r    -     　﻿"
S = "[" + _WS + "]"
NS = "[^" + _WS + "]"
_TRIM = re.compile("^" + S + "+|" + S + "+$")

I = re.IGNORECASE


def trim(s):
    return _TRIM.sub("", s)


def js_len(s):
    """String length as JavaScript counts it (UTF-16 code units)."""
    return len(s.encode("utf-16-le")) // 2


def to_fixed(x, digits):
    """Number.prototype.toFixed for finite numbers."""
    q = Decimal(1).scaleb(-digits)
    d = Decimal(x).quantize(q, rounding=ROUND_HALF_UP)
    out = format(d, "f")
    if out.startswith("-") and d == 0:
        out = out[1:]
    return out


def js_number(x):
    """Return an int when JS would print the number without a decimal point."""
    if isinstance(x, float) and x.is_integer() and abs(x) < 1e21:
        return int(x)
    return x


_INDEX_KEY = re.compile(r"^(0|[1-9]\d*)$")


def js_entries(d):
    """Object.entries order: array-index keys ascending, then insertion order."""
    idx = [k for k in d if _INDEX_KEY.match(k) and int(k) < 4294967295]
    idx.sort(key=int)
    rest = [k for k in d if k not in set(idx)]
    return [(k, d[k]) for k in idx + rest]


SPAM_PATTERNS = [
    r"\bcialis\b",
    r"\bviagra\b",
    r"\btadalafil\b",
    r"\bsildenafil\b",
    r"\bivermectin[ao]?\b",
    r"\bkamagra\b",
    r"\bcasino\b",
    r"\bpoker\b",
    r"\bescort\b",
    r"\breplica watches\b",
    r"\bpayday loan",
]
# JS \b is ASCII-only; Python's is Unicode-aware unless told otherwise.
SPAM_RES = [re.compile(p, re.IGNORECASE | re.ASCII) for p in SPAM_PATTERNS]


def decode(s):
    s = s or ""
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    s = s.replace("&quot;", '"')
    s = re.sub(r"&#0?39;|&apos;", "'", s)
    return s.replace("&nbsp;", " ")


def clean(s):
    s = re.sub(r"<[^>]+>", "", decode(s))
    return trim(re.sub(S + "+", " ", s))


def pick(html, pattern):
    m = re.search(pattern, html, I)
    return clean(m.group(1)) if m else None


def meta_content(html, attr_name, attr_value):
    tag = re.search(
        "<meta[^>]+" + attr_name + "=[\"']" + re.escape(attr_value) + "[\"'][^>]*>", html, I
    )
    if not tag:
        return None
    c = re.search(r"content=[\"']([^\"']*)[\"']", tag.group(0), I)
    return trim(decode(c.group(1))) if c else None


def strip_to_text(html):
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=I)
    html = re.sub(r"<noscript[\s\S]*?</noscript>", " ", html, flags=I)
    html = re.sub(r"<!--[\s\S]*?-->", " ", html)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(S + "+", " ", html)
    return trim(html)


def spam_hits(html):
    hits = []
    for rx in SPAM_RES:
        found = rx.findall(html)
        if found:
            first = rx.search(html).group(0)
            hits.append({"term": first.lower(), "count": len(found)})
    return hits


def summarise(html):
    return {
        "title": pick(html, r"<title[^>]*>([\s\S]*?)</title>"),
        "description": meta_content(html, "name", "description"),
        "h1": pick(html, r"<h1[^>]*>([\s\S]*?)</h1>"),
        "textLength": js_len(strip_to_text(html)),
    }


STOP = set(
    (
        "de la que el en y a los se del las un por con no una su para es al lo como mas "
        "pero sus le ya o este si porque esta entre cuando muy sin sobre tambien me hasta "
        "hay donde quien desde todo nos durante todos uno les ni contra otros ese eso ante "
        "ellos esto mi antes algunos unos yo otro otras otra tanto esa estos mucho quienes "
        "nada muchos cual sea poco ella estar haber estas estaba estamos algunas algo "
        "nosotros puede pueden tiene tienen hacer segun cada mismo tras ademas "
        "the of and to in is it you that was for on are with as be this have from or one "
        "had by not what all were we when your can said there use an each which she do how "
        "their if will up other about out many then them these so some her would make like "
        "him into time has look two more been also may only such most"
    ).split()
)


# ------------------------------------------------------------------ URLs
_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(raw, base=None):
    """Roughly what `new URL(raw, base).href` gives. Raises ValueError if invalid."""
    raw = trim(raw)
    url = urljoin(base, raw) if base else raw
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if not scheme:
        raise ValueError("no scheme")
    if scheme in _DEFAULT_PORTS:
        host = (parts.hostname or "").lower()
        if not host or re.search(r"[\s<>^|]", host):
            raise ValueError("invalid host")
        try:
            port = parts.port
        except ValueError:
            raise ValueError("invalid port")
        netloc = host if ":" not in host else "[" + host + "]"
        if port is not None and port != _DEFAULT_PORTS[scheme]:
            netloc += ":" + str(port)
        if parts.username is not None:
            auth = parts.username
            if parts.password is not None:
                auth += ":" + parts.password
            netloc = auth + "@" + netloc
        path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=~-._")
        return urlunsplit((scheme, netloc, path, parts.query, parts.fragment))
    return url


def hostname_of(raw, base):
    """`new URL(raw, base).hostname`, or None when JS would throw."""
    try:
        parts = urlsplit(urljoin(base, trim(raw)))
        host = (parts.hostname or "").lower()
        if parts.scheme.lower() in _DEFAULT_PORTS and (not host or re.search(r"[\s<>^|]", host)):
            return None  # new URL() throws on an empty or malformed web host
        return host
    except ValueError:
        return None


# ------------------------------------------------------------------ analysis
def analyse_html(html, final_url, headers):
    host = re.sub(r"^www\.", "", (urlsplit(final_url).hostname or "").lower())

    title = pick(html, r"<title[^>]*>([\s\S]*?)</title>") or ""
    description = meta_content(html, "name", "description") or ""
    robots = meta_content(html, "name", "robots")
    viewport = meta_content(html, "name", "viewport")

    canonical_tag = re.search(r"<link[^>]+rel=[\"']canonical[\"'][^>]*>", html, I)
    canonical = None
    if canonical_tag:
        h = re.search(r"href=[\"']([^\"']*)[\"']", canonical_tag.group(0), I)
        canonical = decode(h.group(1)) if h else None
    canonical_self = False
    if canonical:
        try:
            canonical_self = normalize_url(canonical, final_url).rstrip("/") == re.split(
                r"[?#]", final_url
            )[0].rstrip("/")
        except ValueError:
            canonical_self = False

    hreflangs = [
        m.group(1)
        for m in re.finditer(
            r"<link[^>]+rel=[\"']alternate[\"'][^>]*hreflang=[\"']([^\"']+)[\"'][^>]*>", html, I
        )
    ]
    has_x_default = any(h.lower() == "x-default" for h in hreflangs)

    og = {
        "title": meta_content(html, "property", "og:title"),
        "description": meta_content(html, "property", "og:description"),
        "image": meta_content(html, "property", "og:image"),
    }

    lang_m = re.search(r"<html[^>]+lang=[\"']([^\"']+)[\"']", html, I)
    html_lang = lang_m.group(1) if lang_m else None

    headings = {}
    for t in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        headings[t] = len(re.findall("<" + t + r"[" + _WS + ">]", html, I))
    h1s = [clean(m.group(1)) for m in re.finditer(r"<h1[^>]*>([\s\S]*?)</h1>", html, I)]

    text = strip_to_text(html)
    words = [w for w in text.split(" ") if w] if text else []
    word_count = len(words)

    # images
    img_tags = [m.group(0) for m in re.finditer(r"<img\b[^>]*>", html, I | re.ASCII)]
    missing_alt_attr = empty_alt = meaningful_alt = 0
    formats = {}
    for tag in img_tags:
        alt = re.search(r"\balt=[\"']([^\"']*)[\"']", tag, I | re.ASCII)
        if not re.search(r"\balt=", tag, I | re.ASCII):
            missing_alt_attr += 1
        elif not alt or trim(alt.group(1)) == "":
            empty_alt += 1
        else:
            meaningful_alt += 1
        src = re.search(r"\b(?:src|data-src)=[\"']([^\"']+)[\"']", tag, I | re.ASCII)
        if src:
            fm = re.search(r"\.([a-z0-9]+)$", src.group(1).split("?")[0], I)
            f = (fm.group(1) if fm else "other").lower()
            formats[f] = formats.get(f, 0) + 1
    modern_formats = formats.get("webp", 0) + formats.get("avif", 0)
    legacy_formats = formats.get("png", 0) + formats.get("jpg", 0) + formats.get("jpeg", 0)

    # links
    internal = external = nofollow = 0
    for m in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>", html, I | re.ASCII):
        tag = m.group(0)
        if re.search(r"rel=[\"'][^\"']*nofollow", tag, I):
            nofollow += 1
        h = hostname_of(m.group(1), final_url)
        if h is None:
            continue
        h = re.sub(r"^www\.", "", h)
        if not h or h == host:
            internal += 1
        else:
            external += 1

    # structured data
    schema_types = {}

    def walk(n):
        if not n and n != 0:
            return
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            if n.get("@type"):
                t = n["@type"]
                for x in t if isinstance(t, list) else [t]:
                    schema_types[_js_str(x)] = True
            for v in n.values():
                walk(v)

    for m in re.finditer(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>([\s\S]*?)</script>", html, I
    ):
        try:
            walk(json.loads(trim(m.group(1)), parse_constant=_reject_constant))
        except (ValueError, RecursionError):
            schema_types["(invalid JSON-LD)"] = True

    # platform
    cms = "Unknown"
    if re.search(r"wp-content|wp-includes|wp-json", html, I):
        cms = "WordPress"
    elif re.search(r"cdn\.shopify\.com|Shopify\.theme", html, I):
        cms = "Shopify"
    elif re.search(r"webflow", html, I):
        cms = "Webflow"
    elif re.search(r"parastorage|wixstatic", html, I):
        cms = "Wix"
    elif re.search(r"framerusercontent", html, I):
        cms = "Framer"
    elif re.search(r"drupal", html, I):
        cms = "Drupal"

    analytics = []
    if re.search(r"googletagmanager\.com/gtag|gtag/js", html, I):
        analytics.append("Google Analytics 4")
    if re.search(r"googletagmanager\.com/gtm", html, I):
        analytics.append("Google Tag Manager")
    if re.search(r"clarity\.ms", html, I):
        analytics.append("Microsoft Clarity")
    if re.search(r"connect\.facebook\.net", html, I):
        analytics.append("Meta Pixel")

    # keywords (\p{L}\p{N} in JS; Python's \w minus the underscore)
    freq = {}
    for raw in words:
        w = re.sub(r"[^\w\-]|_", "", raw.lower())
        if js_len(w) < 4 or w in STOP:
            continue
        freq[w] = freq.get(w, 0) + 1
    ranked = sorted(js_entries(freq), key=lambda kv: -kv[1])[:10]
    top_keywords = [
        {
            "word": word,
            "count": count,
            "density": to_fixed(count / word_count * 100, 2) if word_count else "0.00",
        }
        for word, count in ranked
    ]

    # mixed language
    sample = _js_slice(text.lower(), 12000)

    def hits(lst):
        return sum(len(re.findall("(^|" + S + ")" + w + "(" + S + "|$)", sample)) for w in lst)

    es_hits = hits(["que", "para", "como", "pero", "porque", "desde", "cuando"])
    en_hits = hits(["the", "that", "with", "from", "which", "because", "when"])
    both_languages = (
        es_hits > 8 and en_hits > 8 and min(es_hits, en_hits) / max(es_hits, en_hits) > 0.2
    )

    security_headers = {}
    for h in [
        "strict-transport-security",
        "x-content-type-options",
        "referrer-policy",
        "content-security-policy",
        "x-frame-options",
        "x-powered-by",
        "server",
    ]:
        security_headers[h] = _header(headers, h)

    return {
        "url": final_url,
        "host": host,
        "title": title,
        "titleLength": js_len(title),
        "description": description,
        "descriptionLength": js_len(description),
        "canonical": canonical,
        "canonicalSelf": canonical_self,
        "robots": robots,
        "viewport": viewport,
        "htmlLang": html_lang,
        "hreflangs": hreflangs,
        "hasXDefault": has_x_default,
        "og": og,
        "h1s": h1s,
        "headings": headings,
        "wordCount": word_count,
        "images": {
            "total": len(img_tags),
            "missingAltAttr": missing_alt_attr,
            "emptyAlt": empty_alt,
            "meaningfulAlt": meaningful_alt,
            "formats": dict(js_entries(formats)),
        },
        "modernFormats": modern_formats,
        "legacyFormats": legacy_formats,
        "links": {
            "internal": internal,
            "external": external,
            "nofollow": nofollow,
            "total": internal + external,
        },
        "schemaTypes": list(schema_types),
        "cms": cms,
        "analytics": analytics,
        "topKeywords": top_keywords,
        "language": {"esHits": es_hits, "enHits": en_hits, "bothLanguages": both_languages},
        "securityHeaders": security_headers,
    }


def _reject_constant(name):
    raise ValueError("JSON.parse does not accept " + name)


def _js_str(x):
    if isinstance(x, bool):
        return "true" if x else "false"
    if x is None:
        return "null"
    if isinstance(x, float):
        return str(js_number(x))
    if isinstance(x, (dict,)):
        return "[object Object]"
    if isinstance(x, list):
        return ",".join(_js_str(v) for v in x)
    return str(x)


def _js_slice(s, n):
    """String.prototype.slice(0, n) counting UTF-16 units."""
    return s if js_len(s) <= n else _cut16(s, n)


def _cut16(s, n):
    units = s.encode("utf-16-le")[: n * 2]
    return units.decode("utf-16-le", errors="ignore")


def _header(headers, name):
    if headers is None:
        return None
    vals = headers.get_all(name) if hasattr(headers, "get_all") else None
    if vals is None:
        v = headers.get(name)
        return v
    return ", ".join(vals) if vals else None


def compare_for_cloaking(browser_html, bot_html):
    a = summarise(browser_html)
    b = summarise(bot_html)

    def norm(s):
        return trim(re.sub(S + "+", " ", (s or "").lower()))

    title_differs = norm(a["title"]) != norm(b["title"])
    desc_differs = norm(a["description"]) != norm(b["description"])
    h1_differs = norm(a["h1"]) != norm(b["h1"])
    size_delta = (
        abs(a["textLength"] - b["textLength"]) / max(a["textLength"], b["textLength"])
        if a["textLength"] and b["textLength"]
        else 0
    )
    bot_spam = spam_hits(bot_html)
    browser_spam = spam_hits(browser_html)
    size_delta = js_number(float(to_fixed(size_delta, 3)))
    return {
        "asBrowser": a,
        "asGooglebot": b,
        "titleDiffers": title_differs,
        "descDiffers": desc_differs,
        "h1Differs": h1_differs,
        "sizeDelta": size_delta,
        "botSpam": bot_spam,
        "browserSpam": browser_spam,
        "suspicious": bool(
            title_differs
            or desc_differs
            or len(bot_spam) > len(browser_spam)
            or size_delta > 0.3
        ),
    }


AI_BOTS = ["GPTBot", "ChatGPT-User", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot"]


def check_robots(body):
    sitemaps = [
        m.group(1)
        for m in re.finditer("^" + S + "*sitemap:" + S + "*(" + NS + "+)", body, re.I | re.M)
    ]
    lines = re.split(r"\r?\n", body)
    ai = {}
    for bot in AI_BOTS:
        blocked = False
        in_block = False
        for line in lines:
            ua = re.match("^" + S + "*user-agent:" + S + "*([^\n\r  ]+)$", line, re.I)
            if ua:
                in_block = trim(ua.group(1)).lower() == bot.lower()
                continue
            if in_block:
                dis = re.match("^" + S + "*disallow:" + S + "*([^\n\r  ]*)$", line, re.I)
                if dis and trim(dis.group(1)) == "/":
                    blocked = True
        ai[bot] = "blocked" if blocked else "allowed"
    return {"sitemaps": sitemaps, "aiCrawlers": ai}


# ------------------------------------------------------------------ fetching
class BlockedHost(Exception):
    pass


def is_private_host(h):
    """The hostname check SEO Lens does, unchanged."""
    h = h.lower()
    if h in ("localhost", "0.0.0.0", "::1", "[::1]") or h.endswith(".localhost") or h.endswith(".internal"):
        return True
    if re.match(r"^(127\.|10\.|192\.168\.|169\.254\.)", h):
        return True
    if re.match(r"^172\.(1[6-9]|2\d|3[01])\.", h):
        return True
    return False


def resolves_private(host):
    """Stricter than the original: also catches names that point inside."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False  # let the fetch fail with a normal "could not reach" message
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            continue
        if not ip.is_global:
            return True
    return False


class _Response:
    def __init__(self, status, url, headers, body):
        self.status = status
        self.url = url
        self.headers = headers
        self.ok = 200 <= status < 300
        self._body = body

    def text(self):
        return self._body.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text())


class _Guard(urllib.request.HTTPRedirectHandler):
    max_redirections = 20  # fetch() follows up to 20

    def __init__(self, allow_private):
        self.allow_private = allow_private

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self.allow_private:
            host = urlsplit(newurl).hostname or ""
            if is_private_host(host) or resolves_private(host):
                raise BlockedHost("Redirects to private and local addresses are not followed.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def http_get(url, headers=None, timeout=25, allow_private=False, limit=15 * 1024 * 1024):
    """A small stand-in for fetch(): follows redirects, never raises on 4xx/5xx."""
    if not allow_private:
        host = urlsplit(url).hostname or ""
        if is_private_host(host) or resolves_private(host):
            raise BlockedHost("Private and local addresses cannot be audited.")
    h = {"accept-encoding": "gzip, deflate", "accept-language": "*"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h, method="GET")
    opener = urllib.request.build_opener(_Guard(allow_private))
    try:
        resp = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        resp = e
    try:
        raw = resp.read(limit + 1)[:limit]
        enc = (resp.headers.get("content-encoding") or "").lower()
        if "gzip" in enc:
            raw = gzip.decompress(raw)
        elif "deflate" in enc:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        status = resp.status if hasattr(resp, "status") and resp.status else resp.getcode()
        return _Response(status, resp.geturl(), resp.headers, raw)
    finally:
        resp.close()


def _err(e):
    if isinstance(e, urllib.error.URLError) and not isinstance(e, urllib.error.HTTPError):
        return str(e.reason)
    return str(e) or e.__class__.__name__


def iso_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_target(raw):
    raw = trim(raw or "")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    return normalize_url(raw)


def run_audit(raw_url, allow_private=False):
    try:
        target = parse_target(raw_url)
    except ValueError:
        return {"ok": False, "error": "That doesn't look like a valid URL."}
    parts = urlsplit(target)
    if parts.scheme not in ("http", "https"):
        return {"ok": False, "error": "Only http and https URLs can be audited."}

    def opts(ua):
        return {"user-agent": ua, "accept": "text/html,*/*"}

    try:
        browser_res = http_get(target, opts(BROWSER_UA), allow_private=allow_private)
        browser_html = browser_res.text()
    except BlockedHost as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001 - mirror fetch's "could not reach"
        return {"ok": False, "error": "Could not reach that URL: " + _err(e)}

    bot_html = ""
    bot_error = None
    try:
        bot_html = http_get(target, opts(GOOGLEBOT_UA), allow_private=allow_private).text()
    except Exception as e:  # noqa: BLE001
        bot_error = _err(e)

    final_url = (browser_res.url or target).split("#")[0]  # fetch drops the fragment
    page = analyse_html(browser_html, final_url, browser_res.headers)
    cloaking = {"error": bot_error} if bot_error else compare_for_cloaking(browser_html, bot_html)

    origin = parts.scheme + "://" + parts.netloc.split("@")[-1]
    try:
        r = http_get(origin + "/robots.txt", opts(BROWSER_UA), allow_private=allow_private)
        if r.ok:
            robots = check_robots(r.text())
            robots["reachable"] = True
        else:
            robots = {"reachable": False, "status": r.status}
    except Exception as e:  # noqa: BLE001
        robots = {"reachable": False, "error": _err(e)}

    return {
        "ok": True,
        "status": browser_res.status,
        "fetchedAt": iso_now(),
        "page": page,
        "cloaking": cloaking,
        "robots": robots,
    }


# ------------------------------------------------------------- Core Web Vitals
def fetch_core_web_vitals(raw_url):
    """Google's PageSpeed Insights API, mobile. Free, no key, rate-limited per IP."""
    try:
        target = parse_target(raw_url)
    except ValueError:
        return {"error": "That doesn't look like a valid URL."}
    api = (
        "https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url="
        + quote(target, safe="-_.!~*'()")
        + "&strategy=mobile&category=performance"
    )
    try:
        r = http_get(api, {}, timeout=90, allow_private=True)
        if not r.ok:
            return {
                "error": "PageSpeed API returned "
                + str(r.status)
                + ". It rate-limits by IP; try again shortly."
            }
        j = r.json()
    except Exception as e:  # noqa: BLE001
        return {"error": "Could not reach the PageSpeed API: " + _err(e)}

    lh = j.get("lighthouseResult") or {}
    audits = lh.get("audits") or {}

    def num(k):
        v = (audits.get(k) or {}).get("numericValue")
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    perf = (lh.get("categories") or {}).get("performance") or {}
    sc = perf.get("score")
    score = (
        _js_round(sc * 100) if isinstance(sc, (int, float)) and not isinstance(sc, bool) else None
    )

    field = None
    m = (j.get("loadingExperience") or {}).get("metrics")
    if m:
        field = {}
        if m.get("LARGEST_CONTENTFUL_PAINT_MS"):
            x = m["LARGEST_CONTENTFUL_PAINT_MS"]
            field["lcp"] = {"value": js_number(x["percentile"] / 1000), "category": x.get("category")}
        if m.get("CUMULATIVE_LAYOUT_SHIFT_SCORE"):
            x = m["CUMULATIVE_LAYOUT_SHIFT_SCORE"]
            field["cls"] = {"value": js_number(x["percentile"] / 100), "category": x.get("category")}
        if m.get("INTERACTION_TO_NEXT_PAINT"):
            x = m["INTERACTION_TO_NEXT_PAINT"]
            field["inp"] = {"value": x["percentile"], "category": x.get("category")}
        if not field:
            field = None

    return {
        "ok": True,
        "score": score,
        "strategy": "mobile",
        "lab": {
            "lcp": num("largest-contentful-paint"),
            "cls": num("cumulative-layout-shift"),
            "tbt": num("total-blocking-time"),
            "fcp": num("first-contentful-paint"),
            "si": num("speed-index"),
        },
        "field": field,
    }


def _js_round(x):
    """Math.round: halves go up (towards +infinity)."""
    import math

    return int(math.floor(x + 0.5))
