"""Shared-password gate (HTTP Basic Auth) wrapping the existing app.

Activates only when the APP_PASSWORD environment variable is set.
When APP_PASSWORD is empty/unset the site behaves exactly as before.
"""
import base64
import os

from cloud_server import app as application

_PW = os.environ.get("APP_PASSWORD")


def _denied(start_response):
    start_response(
        "401 Unauthorized",
        [
            ("WWW-Authenticate", 'Basic realm="Petplan"'),
            ("Content-Type", "text/plain; charset=utf-8"),
        ],
    )
    return [b"Authentication required."]


class _PasswordGate:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        if not _PW:
            return self.wsgi_app(environ, start_response)
        header = environ.get("HTTP_AUTHORIZATION", "")
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8", "ignore")
                supplied = decoded.split(":", 1)[1] if ":" in decoded else ""
                if supplied == _PW:
                    return self.wsgi_app(environ, start_response)
            except Exception:
                pass
        return _denied(start_response)


application.wsgi_app = _PasswordGate(application.wsgi_app)
app = application
