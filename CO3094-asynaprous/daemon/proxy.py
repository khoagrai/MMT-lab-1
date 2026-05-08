"""Threaded reverse proxy for the AsynapRous assignment."""

import socket
import threading
from urllib.parse import urlparse

_ROUTE_LOCK = threading.Lock()
_ROUTE_COUNTER = {}


def _plain_response(status_code, reason, message):
    body = message.encode("utf-8")
    return (
        f"HTTP/1.1 {status_code} {reason}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("utf-8") + body


def _not_found(message="404 Not Found"):
    return _plain_response(404, "Not Found", message)


def _bad_gateway(message="502 Bad Gateway"):
    return _plain_response(502, "Bad Gateway", message)


def _read_http_request(conn):
    """Read HTTP headers and the declared Content-Length body."""
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
                content_length = 0
                for line in header.decode("iso-8859-1", errors="ignore").split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        try:
                            content_length = int(line.split(":", 1)[1].strip())
                        except ValueError:
                            content_length = 0
                        break
            if len(body) >= content_length:
                break

        if len(data) < 4096 and b"\r\n\r\n" in raw and not content_length:
            break

    return b"".join(chunks)


def _extract_host(raw_request):
    text = raw_request.decode("iso-8859-1", errors="ignore")
    for line in text.splitlines():
        if line.lower().startswith("host:"):
            return line.split(":", 1)[1].strip()
    return ""


def _split_host_port(target):
    """Accept 'host:port' or 'http://host:port' and return (host, port)."""
    if not target:
        return None, None
    target = str(target).strip()
    parsed = urlparse(target if "://" in target else "http://" + target)
    return parsed.hostname, parsed.port or 80


def forward_request(host, port, request):
    """Forward raw HTTP request bytes to the selected backend."""
    try:
        with socket.create_connection((host, int(port)), timeout=5.0) as backend:
            backend.sendall(request)
            backend.settimeout(5.0)
            response = []
            while True:
                try:
                    chunk = backend.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                response.append(chunk)
            return b"".join(response) or _bad_gateway("Empty backend response")
    except OSError as exc:
        print(f"[Proxy] forward_request failed {host}:{port}: {exc}")
        return _bad_gateway(str(exc))


def _lookup_route(hostname, routes):
    """Find route by exact host, host without port, or lower-case variant."""
    candidates = [hostname]
    if ":" in hostname:
        candidates.append(hostname.split(":", 1)[0])
    candidates.extend(item.lower() for item in list(candidates))

    for candidate in candidates:
        if candidate in routes:
            return routes[candidate]
    return None


def resolve_routing_policy(hostname, routes):
    """Resolve hostname to backend using single target or round-robin policy."""
    route = _lookup_route(hostname, routes)
    if route is None:
        print(f"[Proxy] no route for Host={hostname!r}")
        return None, None

    proxy_map, policy = route
    targets = [proxy_map] if isinstance(proxy_map, str) else list(proxy_map or [])
    if not targets:
        print(f"[Proxy] empty proxy_pass list for Host={hostname!r}")
        return None, None

    if len(targets) == 1 or policy != "round-robin":
        selected = targets[0]
    else:
        with _ROUTE_LOCK:
            index = _ROUTE_COUNTER.get(hostname, 0)
            selected = targets[index % len(targets)]
            _ROUTE_COUNTER[hostname] = index + 1

    return _split_host_port(selected)


def handle_client(ip, port, conn, addr, routes):
    """Handle one incoming client connection."""
    del ip, port
    try:
        raw_request = _read_http_request(conn)
        if not raw_request:
            return

        hostname = _extract_host(raw_request)
        print(f"[Proxy] {addr} Host: {hostname}")
        resolved_host, resolved_port = resolve_routing_policy(hostname, routes)
        if not resolved_host:
            conn.sendall(_not_found(f"No route for host {hostname}"))
            return

        print(f"[Proxy] forwarding Host {hostname} to {resolved_host}:{resolved_port}")
        conn.sendall(forward_request(resolved_host, resolved_port, raw_request))
    except Exception as exc:  # pragma: no cover - defensive server loop
        print(f"[Proxy] handle_client exception from {addr}: {exc}")
        try:
            conn.sendall(_bad_gateway(str(exc)))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def run_proxy(ip, port, routes):
    """Start proxy and spawn one thread per client connection."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as proxy:
        proxy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        proxy.bind((ip, int(port)))
        proxy.listen(50)
        print(f"[Proxy] Listening on {ip}:{port}")
        print(f"[Proxy] routes={routes}")
        while True:
            conn, addr = proxy.accept()
            thread = threading.Thread(
                target=handle_client,
                args=(ip, port, conn, addr, routes),
                daemon=True,
            )
            thread.start()


def create_proxy(ip, port, routes):
    """Entry point used by start_proxy.py."""
    run_proxy(ip, port, routes)
