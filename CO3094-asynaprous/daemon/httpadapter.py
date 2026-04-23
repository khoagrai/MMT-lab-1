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
daemon.httpadapter
~~~~~~~~~~~~~~~~~

This module provides a http adapter object to manage and persist 
http settings (headers, bodies). The adapter supports both
raw URL paths and RESTful route definitions, and integrates with
Request and Response objects to handle client-server communication.
"""

from .request import Request
from .response import Response
from .dictionary import CaseInsensitiveDict

import asyncio
import inspect

class HttpAdapter:
    """
    A mutable :class:`HTTP adapter <HTTP adapter>` for managing client connections
    and routing requests.

    The `HttpAdapter` class encapsulates the logic for receiving HTTP requests,
    dispatching them to appropriate route handlers, and constructing responses.
    It supports RESTful routing via hooks and integrates with :class:`Request <Request>` 
    and :class:`Response <Response>` objects for full request lifecycle management.
    """

    __attrs__ = [
        "ip",
        "port",
        "conn",
        "connaddr",
        "routes",
        "request",
        "response",
    ]

    def __init__(self, ip, port, conn, connaddr, routes):
        """
        Initialize a new HttpAdapter instance.

        :param ip (str): IP address of the client.
        :param port (int): Port number of the client.
        :param conn (socket): Active socket connection.
        :param connaddr (tuple): Address of the connected client.
        :param routes (dict): Mapping of route paths to handler functions.
        """
        self.ip = ip
        self.port = port
        self.conn = conn
        self.connaddr = connaddr
        self.routes = routes
        self.request = Request()
        self.response = Response()

    def handle_client(self, conn, addr, routes):
        """
        Handle an incoming client connection.
        """
        self.conn = conn        
        self.connaddr = addr
        req = self.request
        resp = self.response

        # Handle the request
        msg = conn.recv(1024).decode()
        req.prepare(msg, routes)
        print("[HttpAdapter] Invoke handle_client connection {}".format(addr))

        response = b""
        if hasattr(req, 'hook') and req.hook:
            # Xử lý đồng bộ (Sync Hook)
            envelop_content = req.hook(headers=req.headers, body=req.body)
            response = resp.build_response(req, envelop_content=envelop_content)
        else:
            response = resp.build_response(req)

        conn.sendall(response)
        conn.close()

    async def handle_client_coroutine(self, reader, writer):
        """
        Handle an incoming client connection using stream reader writer asynchronously.
        """
        req = self.request
        resp = self.response
        addr = writer.get_extra_info("peername")

        print("[HttpAdapter] Invoke handle_client_coroutine connection {}".format(addr))

        try:
            # Đọc dữ liệu bất đồng bộ với Timeout tránh bị treo
            msg = await asyncio.wait_for(reader.read(4096), timeout=10.0)
            
            if not msg:
                print(f"[HttpAdapter] Client {addr} ngắt kết nối sớm.")
                return

            # Chuẩn bị Request object từ dữ liệu nhận được
            req.prepare(msg.decode("utf-8"), self.routes)

            envelop_content = None
            
            # Kiểm tra xem có route hook (API endpoint) được định nghĩa không
            if hasattr(req, 'hook') and req.hook:
                print(f"[HttpAdapter] Kích hoạt hook cho route: {req.url}")
                # Kiểm tra và gọi hàm xử lý tương ứng (Đồng bộ hoặc Bất đồng bộ)
                if inspect.iscoroutinefunction(req.hook):
                    envelop_content = await req.hook(headers=req.headers, body=req.body)
                else:
                    envelop_content = req.hook(headers=req.headers, body=req.body)
            
            # Xây dựng Response (có data trả về từ hook hoặc trả mặc định)
            if envelop_content:
                response = resp.build_response(req, envelop_content=envelop_content)
            else:
                response = resp.build_response(req)

            # Ghi dữ liệu trả về cho client (Không block)
            writer.write(response)
            await writer.drain()

        except asyncio.TimeoutError:
            print(f"[HttpAdapter] Lỗi: Timeout chờ dữ liệu từ {addr}")
        except Exception as e:
            print(f"[HttpAdapter] Lỗi xử lý request từ {addr}: {e}")
            error_msg = b"HTTP/1.1 500 Internal Server Error\r\n\r\n"
            writer.write(error_msg)
            await writer.drain()

    @property
    def extract_cookies(self, req, resp=None):
        """
        Build cookies from the :class:`Request <Request>` headers.
        """
        cookies = {}
        # Sửa lại để lấy headers từ Request object an toàn
        headers = getattr(req, 'headers', [])
        for header in headers:
            if header.startswith("Cookie:"):
                cookie_str = header.split(":", 1)[1].strip()
                for pair in cookie_str.split(";"):
                    if "=" in pair:
                        key, value = pair.strip().split("=", 1)
                        cookies[key] = value
        return cookies

    def build_response(self, req, resp):
        """Builds a :class:`Response <Response>` object"""
        response = Response()

        # Tuỳ thuộc vào backend code (get_encoding_from_headers cần tự định nghĩa hoặc mượn từ thư viện)
        # response.encoding = get_encoding_from_headers(response.headers)
        response.raw = resp
        response.reason = getattr(response.raw, 'reason', "OK")

        if isinstance(req.url, bytes):
            response.url = req.url.decode("utf-8")
        else:
            response.url = req.url

        # Add new cookies from the server.
        response.cookies = self.extract_cookies(req)

        # Give the Response some context.
        response.request = req
        response.connection = self

        return response

    def build_json_response(self, req, resp):
        """Builds a :class:`Response <Response>` object from JSON data"""
        response = Response(req)

        response.raw = resp

        if isinstance(req.url, bytes):
            response.url = req.url.decode("utf-8")
        else:
            response.url = req.url

        response.request = req
        response.connection = self

        return response

    def add_headers(self, request):
        """
        Add headers to the request.
        """
        pass

    def build_proxy_headers(self, proxy):
        """Returns a dictionary of the headers to add to any request sent
        through a proxy. 
        """
        headers = {}
        username, password = ("user1", "password")

        if username:
            headers["Proxy-Authorization"] = (username, password)

        return headers