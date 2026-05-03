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
This module provides a HTTP adapter object to manage and persist
http settings (headers, bodies).
"""

import asyncio
import inspect

from .request import Request
from .response import Response


class HttpAdapter:
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
        self.ip = ip
        self.port = port
        self.conn = conn
        self.connaddr = connaddr
        self.routes = routes or {}
        self.request = Request()
        self.response = Response()

    def _read_from_socket(self, conn):
        chunks = []
        conn.settimeout(2.0)

        while True:
            data = conn.recv(4096)
            if not data:
                break
            chunks.append(data)

            # small requests only, enough for assignment auth/chat demo
            if len(data) < 4096:
                break

        return b"".join(chunks).decode("utf-8", errors="ignore")

    def _invoke_hook_sync(self, req):
        if not req.hook:
            return None

        print(
            "[HttpAdapter] invoking sync hook method={} path={}".format(
                req.method, req.path
            )
        )

        result = req.hook(headers=req.headers, body=req.body)

        if inspect.isawaitable(result):
            return asyncio.run(result)

        return result

    async def _invoke_hook_async(self, req):
        if not req.hook:
            return None

        print(
            "[HttpAdapter] invoking async hook method={} path={}".format(
                req.method, req.path
            )
        )

        result = req.hook(headers=req.headers, body=req.body)

        if inspect.isawaitable(result):
            return await result

        return result

    def handle_client(self, conn, addr, routes):
        self.conn = conn
        self.connaddr = addr
        self.routes = routes or {}

        try:
            raw_request = self._read_from_socket(conn)
            if not raw_request:
                conn.close()
                return

            req = self.request
            resp = self.response

            req.prepare(raw_request, self.routes)

            print("[HttpAdapter] handle_client connection={}".format(addr))

            handler_result = self._invoke_hook_sync(req) if req.hook else None
            response_bytes = resp.build_response(req, handler_result)

            conn.sendall(response_bytes)
        except Exception as exc:
            print("[HttpAdapter] handle_client exception: {}".format(exc))
            fallback = (
                "HTTP/1.1 500 Internal Server Error\r\n"
                "Content-Type: text/plain; charset=utf-8\r\n"
                "Content-Length: 21\r\n"
                "Connection: close\r\n"
                "\r\n"
                "Internal Server Error"
            ).encode("utf-8")
            try:
                conn.sendall(fallback)
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    async def handle_client_coroutine(self, reader, writer):
        try:
            raw_request = await reader.read(4096)
            if not raw_request:
                writer.close()
                await writer.wait_closed()
                return

            req = self.request
            resp = self.response

            addr = writer.get_extra_info("peername")
            print("[HttpAdapter] handle_client_coroutine connection={}".format(addr))

            req.prepare(raw_request.decode("utf-8", errors="ignore"), self.routes)

            handler_result = await self._invoke_hook_async(req) if req.hook else None
            response_bytes = resp.build_response(req, handler_result)

            writer.write(response_bytes)
            await writer.drain()
        except Exception as exc:
            print("[HttpAdapter] handle_client_coroutine exception: {}".format(exc))
            fallback = (
                "HTTP/1.1 500 Internal Server Error\r\n"
                "Content-Type: text/plain; charset=utf-8\r\n"
                "Content-Length: 21\r\n"
                "Connection: close\r\n"
                "\r\n"
                "Internal Server Error"
            ).encode("utf-8")
            try:
                writer.write(fallback)
                await writer.drain()
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass