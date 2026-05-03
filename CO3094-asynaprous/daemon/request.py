# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#
"""
daemon.request
~~~~~~~~~~~~~~~~~
This module provides a Request object to manage and persist request settings
(cookies, auth, proxies).
"""

import base64
from urllib.parse import urlsplit

from .dictionary import CaseInsensitiveDict


class Request:
    __attrs__ = [
        "method",
        "url",
        "path",
        "version",
        "headers",
        "body",
        "_raw_headers",
        "_raw_body",
        "reason",
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
        self.reason = None
        self.cookies = CaseInsensitiveDict()
        self.auth = None
        self.routes = {}
        self.hook = None

    def extract_request_line(self, request):
        try:
            lines = request.splitlines()
            first_line = lines[0].strip()
            method, path, version = first_line.split()
            return method.upper(), path, version
        except Exception:
            return None, None, None

    def _normalize_path(self, path):
        if not path:
            return "/index.html"

        parsed = urlsplit(path)
        normalized = parsed.path or "/"

        if normalized == "/":
            return "/index.html"

        if len(normalized) > 1 and normalized.endswith("/"):
            normalized = normalized[:-1]

        return normalized

    def prepare_headers(self, request):
        lines = request.split("\r\n")
        headers = CaseInsensitiveDict()

        for line in lines[1:]:
            if not line.strip():
                continue
            if ": " not in line:
                continue
            key, value = line.split(": ", 1)
            headers[key.lower()] = value

        return headers

    def fetch_headers_body(self, request):
        parts = request.split("\r\n\r\n", 1)
        _headers = parts[0]
        _body = parts[1] if len(parts) > 1 else ""
        return _headers, _body

    def prepare(self, request, routes=None):
        print("[Request] prepare request msg={}".format(request))

        self.method, raw_path, self.version = self.extract_request_line(request)
        self.path = self._normalize_path(raw_path)
        self.url = self.path

        self._raw_headers, self._raw_body = self.fetch_headers_body(request)
        self.headers = self.prepare_headers(self._raw_headers)
        self.body = self._raw_body

        self.routes = routes or {}
        self.hook = self.routes.get((self.method, self.path))

        self.cookies = self.extract_cookies()
        self.auth = self.prepare_auth_from_headers()

        print(
            "[Request] method={} path={} version={} hook={}".format(
                self.method, self.path, self.version, self.hook
            )
        )

        return self

    def extract_cookies(self):
        cookies = CaseInsensitiveDict()
        cookie_header = self.headers.get("cookie", "")

        if not cookie_header:
            return cookies

        for pair in cookie_header.split(";"):
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            cookies[key.strip()] = value.strip()

        return cookies

    def prepare_body(self, data=None, files=None, json=None):
        body = ""
        if json is not None:
            import json as _json
            body = _json.dumps(json)
        elif data is not None:
            body = str(data)

        self.body = body
        self.prepare_content_length(body)
        return body

    def prepare_content_length(self, body):
        if self.headers is None:
            self.headers = CaseInsensitiveDict()

        if body is None:
            body = ""

        if isinstance(body, str):
            body = body.encode("utf-8")

        self.headers["content-length"] = str(len(body))
        return self.headers["content-length"]

    def prepare_auth_from_headers(self):
        authorization = self.headers.get("authorization", "")
        if not authorization:
            return None

        if not authorization.lower().startswith("basic "):
            return authorization

        try:
            token = authorization.split(" ", 1)[1].strip()
            decoded = base64.b64decode(token).decode("utf-8")
            username, password = decoded.split(":", 1)
            return {"type": "basic", "username": username, "password": password}
        except Exception:
            return None

    def prepare_auth(self, auth, url=""):
        self.auth = auth
        return auth

    def prepare_cookies(self, cookies):
        if self.headers is None:
            self.headers = CaseInsensitiveDict()
        self.headers["cookie"] = cookies
        return cookies