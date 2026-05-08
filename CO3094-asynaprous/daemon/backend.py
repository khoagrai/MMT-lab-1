"""Backend daemon with selectable non-blocking/concurrency mode."""

import asyncio
import inspect
import os
import selectors
import socket
import threading

from .httpadapter import HttpAdapter

DEFAULT_ASYNC_MODE = "threading"
VALID_MODES = {"threading", "callback", "coroutine"}


def _selected_mode():
    mode = os.getenv("ASYNC_MODE", DEFAULT_ASYNC_MODE).strip().lower()
    if mode not in VALID_MODES:
        print(f"[Backend] Invalid ASYNC_MODE={mode!r}; fallback to threading")
        return "threading"
    return mode


def _print_routes(routes):
    if not routes:
        return
    print("[Backend] route settings")
    for key, value in routes.items():
        marker = "**ASYNC** " if inspect.iscoroutinefunction(value) else ""
        print(f" + {key}: {marker}{value}")


def handle_client(ip, port, conn, addr, routes):
    """Handle one accepted client connection."""
    print(f"[Backend] accepted connection from {addr}")
    daemon = HttpAdapter(ip, port, conn, addr, routes)
    daemon.handle_client(conn, addr, routes)


def _accept_callback(server, ip, port, routes):
    """Selector callback for accepting ready connections."""
    conn, addr = server.accept()
    print(f"[Backend] callback accepted connection from {addr}")
    thread = threading.Thread(
        target=handle_client,
        args=(ip, port, conn, addr, routes),
        daemon=True,
    )
    thread.start()


async def async_server(ip="0.0.0.0", port=7000, routes=None):
    """Run coroutine-based asyncio server."""
    routes = routes or {}

    async def _handle(reader, writer):
        addr = writer.get_extra_info("peername")
        print(f"[Backend] coroutine accepted connection from {addr}")
        daemon = HttpAdapter(ip, port, None, addr, routes)
        await daemon.handle_client_coroutine(reader, writer)

    print(f"[Backend] coroutine listening on {ip}:{port}")
    _print_routes(routes)
    server = await asyncio.start_server(_handle, ip, int(port))
    async with server:
        await server.serve_forever()


def _run_threading(server, ip, port, routes):
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(
            target=handle_client,
            args=(ip, port, conn, addr, routes),
            daemon=True,
        )
        thread.start()


def _run_callback(server, ip, port, routes):
    selector = selectors.DefaultSelector()
    server.setblocking(False)
    selector.register(server, selectors.EVENT_READ, (_accept_callback, ip, port, routes))
    while True:
        for key, _ in selector.select(timeout=None):
            callback, cb_ip, cb_port, cb_routes = key.data
            callback(key.fileobj, cb_ip, cb_port, cb_routes)


def run_backend(ip, port, routes=None):
    """Start backend in threading, callback, or coroutine mode."""
    routes = routes or {}
    mode = _selected_mode()
    print(f"[Backend] run_backend mode={mode} routes={routes}")

    if mode == "coroutine":
        asyncio.run(async_server(ip, port, routes))
        return

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((ip, int(port)))
        server.listen(50)
        print(f"[Backend] Listening on {ip}:{port}")
        _print_routes(routes)

        if mode == "callback":
            _run_callback(server, ip, port, routes)
        else:
            _run_threading(server, ip, port, routes)


def create_backend(ip, port, routes=None):
    """Entry point for backend process."""
    run_backend(ip, port, routes or {})
