#
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

This module provides a Request object to manage and persist 
request settings (cookies, auth, proxies).
"""
from .dictionary import CaseInsensitiveDict

class Request():
    """The fully mutable "class" `Request <Request>` object,
    containing the exact bytes that will be sent to the server.
    """
    __attrs__ = [
        "method",
        "url",
        "headers",
        "body",
        "_raw_headers",
        "_raw_body",
        "reason",
        "cookies",
        "body",
        "routes",
        "hook",
    ]

    def __init__(self):
        self.method = None
        self.url = None
        # Khởi tạo headers bằng CaseInsensitiveDict để tránh lỗi NoneType
        self.headers = CaseInsensitiveDict() 
        self.path = None        
        self.cookies = {}
        self.body = None
        self._raw_headers = None
        self._raw_body = None
        self.routes = {}
        self.hook = None

    def extract_request_line(self, request):
        try:
            lines = request.splitlines()
            if not lines:
                return None, None, None
            first_line = lines[0]
            method, path, version = first_line.split()

            if path == '/':
                path = '/index.html'
        except Exception:
            return None, None, None

        return method, path, version
             
    def prepare_headers(self, request):
        """Prepares the given HTTP headers."""
        lines = request.split('\r\n')
        headers = CaseInsensitiveDict()
        for line in lines[1:]:
            if ':' in line:
                key, val = line.split(':', 1)
                # Dùng .strip() để xóa khoảng trắng thừa thay vì hardcode ': '
                headers[key.strip()] = val.strip()
        return headers

    def fetch_headers_body(self, request):
        """Prepares the given HTTP headers."""
        # Split request into header section and body section
        parts = request.split("\r\n\r\n", 1)  # split once at blank line

        _headers = parts[0]
        _body = parts[1] if len(parts) > 1 else ""
        return _headers, _body

    def prepare(self, request, routes=None):
        """Prepares the entire request with the given parameters."""

        # 1. Bóc tách Header và Body (SỬA LỖI Ở ĐÂY)
        self._raw_headers, self._raw_body = self.fetch_headers_body(request)

        # 2. Lấy Method, Path
        self.method, self.path, self.version = self.extract_request_line(self._raw_headers)
        print("[Request] {} path {} version {}".format(self.method, self.path, self.version))

        # 3. Parse Header thành Dictionary (QUAN TRỌNG: Vá lỗi NoneType)
        self.headers = self.prepare_headers(self._raw_headers)
        
        # 4. Gán Body
        self.body = self._raw_body

        # 5. Xử lý Hook (Route)
        if routes is not None and routes != {}:
            self.routes = routes
            print("[Request] Routing METHOD {} path {}".format(self.method, self.path))
            self.hook = routes.get((self.method, self.path))
            if self.hook:
                print("[Request] Hook has request {}".format(self.hook))

        # 6. Xử lý Cookie
        cookies_str = self.headers.get('Cookie', '')
        self.cookies = cookies_str

        return

    def prepare_body(self, data, files, json=None):
        self.prepare_content_length(self.body)
        self.body = data # Fix lỗi logic gán sai body
        return

    def prepare_content_length(self, body):
        self.headers["Content-Length"] = str(len(body)) if body else "0"
        return

    def prepare_auth(self, auth, url=""):
        return

    def prepare_cookies(self, cookies):
        self.headers["Cookie"] = cookies