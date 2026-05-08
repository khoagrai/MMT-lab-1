"""HTTP request parser used by HttpAdapter."""

import base64
from urllib.parse import urlparse

from .dictionary import CaseInsensitiveDict


class Request:
    """Mutable request object containing parsed HTTP request data."""

    __attrs__ = [
        "method",
        "url",
        "path",
        "version",
        "headers",
        "body",
        "_raw_headers",
        "_raw_body",
        "cookies",
        "auth",
        "routes",
        "hook",
    ]

    def __init__(self):
        self.method = None
        self.url = None
        self.path = None
        self.version = None
        self.headers = CaseInsensitiveDict()
        self.body = ""
        self._raw_headers = ""
        self._raw_body = ""
        self.cookies = {}
        self.auth = None
        self.routes = {}
        self.hook = None

    def extract_request_line(self, request):
        try:
            first_line = request.splitlines()[0]
            method, raw_path, version = first_line.split()
        except Exception:
            return None, None, None

        parsed = urlparse(raw_path)
        path = parsed.path or "/"
        if path == "/":
            path = "/index.html"
        return method.upper(), path, version

    def fetch_headers_body(self, request):
        parts = request.split("\r\n\r\n", 1)
        headers = parts[0]
        body = parts[1] if len(parts) > 1 else ""
        return headers, body

    def prepare_headers(self, raw_headers):
        headers = CaseInsensitiveDict()
        for line in raw_headers.split("\r\n")[1:]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
        return headers

    def prepare_cookies(self, cookies):
        parsed = {}
        if not cookies:
            return parsed
        for item in cookies.split(";"):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            parsed[key.strip()] = value.strip()
        self.cookies = parsed
        return parsed

    def prepare_auth(self, auth, url=""):
        del url
        if not auth:
            self.auth = None
            return None
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "basic" or not token:
            self.auth = None
            return None
        try:
            decoded = base64.b64decode(token).decode("utf-8")
            username, password = decoded.split(":", 1)
            self.auth = (username, password)
        except Exception:
            self.auth = None
        return self.auth

    def prepare_body(self, data, files=None, json=None):
        del files, json
        self.body = data or ""
        return self.body

    def prepare_content_length(self, body):
        return len(body or "")

    def prepare(self, request, routes=None):
        """Parse raw HTTP request and bind route handler."""
        self.method, self.path, self.version = self.extract_request_line(request)
        self.url = self.path
        self._raw_headers, self._raw_body = self.fetch_headers_body(request)
        self.headers = self.prepare_headers(self._raw_headers)
        self.body = self._raw_body
        self.prepare_cookies(self.headers.get("Cookie", ""))
        self.prepare_auth(self.headers.get("Authorization", ""), self.url)

        self.routes = routes or {}
        self.hook = None
        if self.routes and self.method and self.path:
            self.hook = self.routes.get((self.method, self.path))
            if self.hook is None and not self.path.endswith("/"):
                self.hook = self.routes.get((self.method, self.path + "/"))
            if self.hook is None and self.path.endswith("/"):
                self.hook = self.routes.get((self.method, self.path.rstrip("/")))

        print(f"[Request] {self.method} {self.path} hook={bool(self.hook)}")
        return self
