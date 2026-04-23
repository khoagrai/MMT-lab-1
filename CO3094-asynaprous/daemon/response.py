#
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

This module provides a :class: `Response <Response>` object to manage and persist 
response settings (cookies, auth, proxies), and to construct HTTP responses
based on incoming requests. 

The current version supports MIME type detection, content loading and header formatting
"""
import datetime
import os
import mimetypes
from .dictionary import CaseInsensitiveDict

# BASE_DIR để trống nghĩa là đường dẫn tương đối từ thư mục gốc chạy file start_backend.py
BASE_DIR = ""

class Response():   
    """The :class:`Response <Response>` object, which contains a
    server's response to an HTTP request.
    """

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
        "reason",
    ]


    def __init__(self, request=None):
        """
        Initializes a new :class:`Response <Response>` object.
        """
        self._content = b""
        self._header = b""
        self._content_consumed = False
        self._next = None

        self.status_code = 200
        self.headers = {}
        self.url = None
        self.encoding = None
        self.history = []
        self.reason = "OK"
        self.cookies = CaseInsensitiveDict()
        self.elapsed = datetime.timedelta(0)
        self.request = None


    def get_mime_type(self, path):
        """Determines the MIME type of a file based on its path."""
        try:
            mime_type, _ = mimetypes.guess_type(path)
        except Exception:
            return 'application/octet-stream'
        return mime_type or 'application/octet-stream'


    def prepare_content_type(self, mime_type='text/html'):
        """Prepares the Content-Type header and determines the base directory"""
        base_dir = BASE_DIR

        if not hasattr(self, "headers") or self.headers is None:
            self.headers = {}

        try:
            main_type, sub_type = mime_type.split('/', 1)
        except ValueError:
            main_type, sub_type = 'application', 'octet-stream'

        print("[Response] Processing main_type={} sub_type={}".format(main_type,sub_type))
        self.headers['Content-Type'] = mime_type

        # Phân luồng thư mục dựa vào loại file
        if main_type == 'text':
            if sub_type == 'plain' or sub_type == 'css':
                base_dir = os.path.join(BASE_DIR, "static/")
            elif sub_type == 'html':
                base_dir = os.path.join(BASE_DIR, "www/")
            else:
                base_dir = os.path.join(BASE_DIR, "static/")
        elif main_type == 'image':
            base_dir = os.path.join(BASE_DIR, "static/")
        elif main_type == 'application':
            if sub_type == 'json':
                pass # JSON thường trả về trực tiếp từ API WebApp
            else:
                base_dir = os.path.join(BASE_DIR, "static/")
        else:
            base_dir = os.path.join(BASE_DIR, "static/")

        return base_dir


    def build_content(self, path, base_dir):
        """Loads the objects file from storage space."""
        # Fix lỗi dấu '/' ở đầu path
        clean_path = path.lstrip('/')
        filepath = os.path.join(base_dir, clean_path)

        print("[Response] Serving the object at location {}".format(filepath))
        
        try:
            with open(filepath, "rb") as f:
               content = f.read()
        except Exception as e:
            print("[Response] Lỗi không tìm thấy file hoặc quyền truy cập: {}".format(e))
            return -1, b""
        return len(content), content


    def build_response_header(self, request):
        """Constructs the HTTP response headers."""
        # Fix lỗi NoneType bằng cách gán {} nếu request.headers là None
        reqhdr = getattr(request, 'headers', {})
        if reqhdr is None:
            reqhdr = {}

        # Lấy Content-Length từ dữ liệu
        content_length = len(self._content) if self._content else 0

        # Build dynamic headers
        response_headers = {
            "Content-Type": self.headers.get('Content-Type', 'text/html'),
            "Content-Length": str(content_length),
            "Connection": reqhdr.get("Connection", "close"),
            "Server": "AsynapRous/1.0",
            "Date": datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        }

        # Nếu có cookie muốn set (ví dụ đăng nhập), gỡ comment dòng dưới:
        # if hasattr(self, 'cookies') and len(self.cookies) > 0:
        #     # Cấu hình chuỗi Set-Cookie ...

        # Ghép thành chuỗi HTTP Header chuẩn
        fmt_header = f"HTTP/1.1 {self.status_code} {self.reason}\r\n"
        for key, value in response_headers.items():
            fmt_header += f"{key}: {value}\r\n"
        fmt_header += "\r\n" # Ký tự rỗng báo hiệu kết thúc Header

        return fmt_header.encode('utf-8')


    def build_notfound(self):
        """Constructs a standard 404 Not Found HTTP response."""
        self.status_code = 404
        self.reason = "Not Found"
        return (
            "HTTP/1.1 404 Not Found\r\n"
            "Content-Type: text/html\r\n"
            "Content-Length: 43\r\n"
            "Connection: close\r\n"
            "\r\n"
            "<h1>404 Not Found</h1><p>File missing</p>"
        ).encode('utf-8')


    def build_response(self, request, envelop_content=None):
        """Builds a full HTTP response including headers and content based on the request."""
        print("[Response] Start build response with req {}".format(request.path))

        path = getattr(request, 'path', '/')
        # Tự động trỏ '/' về 'index.html'
        if path == '/':
            path = '/index.html'

        mime_type = self.get_mime_type(path)
        base_dir = self.prepare_content_type(mime_type=mime_type)

        # Ưu tiên lấy content từ API Hook nếu có (envelop_content)
        if envelop_content is not None:
            if isinstance(envelop_content, str):
                self._content = envelop_content.encode('utf-8')
            else:
                self._content = envelop_content
        else:
            # Nếu không có từ API, tiến hành đọc file tĩnh từ ổ cứng
            content_len, self._content = self.build_content(path, base_dir)
            if content_len == -1:
                return self.build_notfound()

        # Sau khi có content, tiến hành sinh Header
        self._header = self.build_response_header(request)

        # Trả về chuỗi byte hoàn chỉnh (Header + Body)
        return self._header + self._content