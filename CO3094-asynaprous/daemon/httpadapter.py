"""HTTP adapter for parsing requests, invoking routes, and sending responses."""

import asyncio
import inspect

from .request import Request
from .response import Response


class HttpAdapter:
    """Small adapter that dispatches a socket request to a route handler."""

    __attrs__ = ["ip", "port", "conn", "connaddr", "routes", "request", "response"]

    def __init__(self, ip, port, conn, connaddr, routes):
        self.ip = ip
        self.port = port
        self.conn = conn
        self.connaddr = connaddr
        self.routes = routes or {}
        self.request = Request()
        self.response = Response()

    @staticmethod
    def _content_length_from_header(header_bytes):
        content_length = 0
        text = header_bytes.decode("iso-8859-1", errors="ignore")
        for line in text.split("\r\n"):
            if line.lower().startswith("content-length:"):
                try:
                    content_length = int(line.split(":", 1)[1].strip())
                except ValueError:
                    content_length = 0
                break
        return content_length

    def _read_from_socket(self, conn):
        chunks = []
        conn.settimeout(3.0)
        content_length = None
        while True:
            data = conn.recv(4096)
            if not data:
                break
            chunks.append(data)
            raw = b"".join(chunks)
            if b"\r\n\r\n" in raw:
                header, body = raw.split(b"\r\n\r\n", 1)
                if content_length is None:
                    content_length = self._content_length_from_header(header)
                if len(body) >= content_length:
                    break
            if len(data) < 4096 and b"\r\n\r\n" in raw and not content_length:
                break
        return b"".join(chunks).decode("utf-8", errors="ignore")

    async def _read_from_reader(self, reader):
        header = await reader.readuntil(b"\r\n\r\n")
        content_length = self._content_length_from_header(header)
        body = await reader.readexactly(content_length) if content_length else b""
        return (header + body).decode("utf-8", errors="ignore")

    def _invoke_hook_sync(self, req):
        if not req.hook:
            return None
        print(f"[HttpAdapter] invoking sync hook method={req.method} path={req.path}")
        result = req.hook(headers=req.headers, body=req.body)
        if inspect.isawaitable(result):
            return asyncio.run(result)
        return result

    async def _invoke_hook_async(self, req):
        if not req.hook:
            return None
        print(f"[HttpAdapter] invoking async hook method={req.method} path={req.path}")
        result = req.hook(headers=req.headers, body=req.body)
        if inspect.isawaitable(result):
            return await result
        return result

    @staticmethod
    def _fallback_response():
        body = b"Internal Server Error"
        return (
            "HTTP/1.1 500 Internal Server Error\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("utf-8") + body

    def handle_client(self, conn, addr, routes):
        self.conn = conn
        self.connaddr = addr
        self.routes = routes or {}
        try:
            raw_request = self._read_from_socket(conn)
            if not raw_request:
                return
            req = self.request
            resp = self.response
            req.prepare(raw_request, self.routes)
            print(f"[HttpAdapter] handle_client connection={addr}")
            handler_result = self._invoke_hook_sync(req) if req.hook else None
            conn.sendall(resp.build_response(req, handler_result))
        except Exception as exc:
            print(f"[HttpAdapter] handle_client exception: {exc}")
            try:
                conn.sendall(self._fallback_response())
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    async def handle_client_coroutine(self, reader, writer):
        try:
            raw_request = await self._read_from_reader(reader)
            if not raw_request:
                return
            req = self.request
            resp = self.response
            addr = writer.get_extra_info("peername")
            print(f"[HttpAdapter] handle_client_coroutine connection={addr}")
            req.prepare(raw_request, self.routes)
            handler_result = await self._invoke_hook_async(req) if req.hook else None
            writer.write(resp.build_response(req, handler_result))
            await writer.drain()
        except Exception as exc:
            print(f"[HttpAdapter] handle_client_coroutine exception: {exc}")
            try:
                writer.write(self._fallback_response())
                await writer.drain()
            except Exception:
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
