# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course.
#
# AsynApRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#
"""
daemon.response
~~~~~~~~~~~~~~~~~
This module provides a Response object to manage and persist response settings
(cookies, auth, proxies), and to construct HTTP responses based on incoming
requests.
"""

import datetime
import json
import mimetypes
import os

from .dictionary import CaseInsensitiveDict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Response:
    __attrs__ = [
        "_content",
        "_header",
        "status_code",
        "method",
        "headers",
        "url",
        "history",
        "encoding",
        "reason",
        "cookies",
        "elapsed",
        "request",
        "body",
    ]

    STATUS_TEXT = {
        200: "OK",
        201: "Created",
        204: "No Content",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        500: "Internal Server Error",
    }

    def __init__(self, request=None):
        self._content = b""
        self._header = b""
        self.status_code = 200
        self.method = None
        self.headers = CaseInsensitiveDict()
        self.url = None
        self.history = []
        self.encoding = "utf-8"
        self.reason = "OK"
        self.cookies = CaseInsensitiveDict()
        self.elapsed = datetime.timedelta(0)
        self.request = request
        self.body = b""

    def get_mime_type(self, path):
        try:
            mime_type, _ = mimetypes.guess_type(path)
        except Exception:
            return "application/octet-stream"
        return mime_type or "application/octet-stream"

    def prepare_content_type(self, mime_type="text/html"):
        main_type, sub_type = mime_type.split("/", 1)

        if main_type == "text":
            if sub_type == "html":
                base_dir = os.path.join(PROJECT_ROOT, "www")
            else:
                base_dir = os.path.join(PROJECT_ROOT, "static")
        elif main_type == "image":
            base_dir = os.path.join(PROJECT_ROOT, "static")
        elif main_type == "application":
            if sub_type == "javascript":
                base_dir = os.path.join(PROJECT_ROOT, "static")
            else:
                base_dir = PROJECT_ROOT
        else:
            base_dir = PROJECT_ROOT

        self.headers["Content-Type"] = mime_type
        return base_dir

    def build_content(self, path, base_dir):
        filepath = os.path.join(base_dir, path.lstrip("/"))
        print("[Response] Serving object at {}".format(filepath))

        try:
            with open(filepath, "rb") as file_obj:
                content = file_obj.read()
            return len(content), content
        except Exception as exc:
            print("[Response] build_content exception: {}".format(exc))
            return -1, b""

    def build_notfound(self):
        body = b"404 Not Found"
        self.status_code = 404
        self.reason = self.STATUS_TEXT[404]
        self.headers["Content-Type"] = "text/plain; charset=utf-8"
        self.headers["Content-Length"] = str(len(body))
        self.headers["Connection"] = "close"

        header = self.build_response_header(None)
        return header + body

    def build_response_header(self, request):
        status_code = int(self.status_code or 200)
        reason = self.STATUS_TEXT.get(status_code, "OK")
        self.reason = reason

        lines = [
            "HTTP/1.1 {} {}".format(status_code, reason),
        ]

        if "Content-Type" not in self.headers:
            self.headers["Content-Type"] = "text/plain; charset=utf-8"

        if "Connection" not in self.headers:
            self.headers["Connection"] = "close"

        for key, value in self.headers.items():
            lines.append("{}: {}".format(key, value))

        lines.append("")
        lines.append("")

        return "\r\n".join(lines).encode("utf-8")

    def _normalize_dynamic_response(self, envelop_content):
        status_code = 200
        extra_headers = CaseInsensitiveDict()
        payload = envelop_content

        if isinstance(envelop_content, dict) and (
            "status_code" in envelop_content
            or "headers" in envelop_content
            or "body" in envelop_content
        ):
            status_code = int(envelop_content.get("status_code", 200))
            extra_headers.update(envelop_content.get("headers", {}))
            payload = envelop_content.get("body", {})
        elif isinstance(envelop_content, tuple) and len(envelop_content) == 3:
            status_code, headers, payload = envelop_content
            extra_headers.update(headers or {})

        if isinstance(payload, (dict, list)):
            body_bytes = json.dumps(payload).encode("utf-8")
            content_type = extra_headers.get(
                "Content-Type",
                "application/json; charset=utf-8",
            )
        elif isinstance(payload, bytes):
            body_bytes = payload
            content_type = extra_headers.get(
                "Content-Type",
                "application/json; charset=utf-8",
            )
        elif payload is None:
            body_bytes = b""
            content_type = extra_headers.get(
                "Content-Type",
                "text/plain; charset=utf-8",
            )
        else:
            body_bytes = str(payload).encode("utf-8")
            content_type = extra_headers.get(
                "Content-Type",
                "text/plain; charset=utf-8",
            )

        self.status_code = int(status_code)
        self.headers = CaseInsensitiveDict()
        self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(body_bytes))
        self.headers["Connection"] = "close"

        for key, value in extra_headers.items():
            self.headers[key] = value

        return self.build_response_header(self.request) + body_bytes

    def build_response(self, request, envelop_content=None):
        print("[Response] Start build_response path={}".format(request.path))
        self.request = request
        self.url = request.path
        self.method = request.method

        if envelop_content is not None:
            return self._normalize_dynamic_response(envelop_content)

        path = request.path
        mime_type = self.get_mime_type(path)

        if path.endswith(".html") or mime_type == "text/html":
            base_dir = self.prepare_content_type("text/html")
        elif mime_type == "text/css":
            base_dir = self.prepare_content_type("text/css")
        elif mime_type in ("application/javascript", "text/javascript"):
            base_dir = self.prepare_content_type("application/javascript")
        elif mime_type.startswith("image/"):
            base_dir = self.prepare_content_type(mime_type)
        else:
            base_dir = self.prepare_content_type(mime_type)

        content_length, content = self.build_content(path, base_dir)
        if content_length < 0:
            return self.build_notfound()

        self.status_code = 200
        self.reason = self.STATUS_TEXT[200]
        self.headers["Content-Length"] = str(content_length)
        self.headers["Connection"] = "close"

        header = self.build_response_header(request)
        return header + content