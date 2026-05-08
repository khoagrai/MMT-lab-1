"""Hybrid client-server + P2P chat application for AsynapRous."""

import json
import secrets
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs

from daemon import AsynapRous

app = AsynapRous()

USERS = {
    "admin": "123456",
    "khoi": "123456",
    "user1": "123456",
    "user2": "123456",
}

SESSION_COOKIE_NAME = "session_id"
SESSION_TTL_SECONDS = 3600
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()

PEER_TIMEOUT = 120
PEERS = {}
CHANNELS = {}
TRACKER_LOCK = threading.Lock()

CHAT_HISTORY = []
HISTORY_LOCK = threading.Lock()


def route(path, methods):
    """Register a route and also register the trailing-slash alias."""
    def decorator(func):
        for method in methods:
            app.routes[(method.upper(), path)] = func
            if not path.endswith("/"):
                app.routes[(method.upper(), path + "/")] = func
        return func
    return decorator


def _normalize_headers(headers):
    if not headers:
        return {}
    try:
        items = headers.items()
    except AttributeError:
        items = dict(headers).items()
    return {str(key).lower(): str(value) for key, value in items}


def _parse_body(body):
    if body is None:
        return {}
    if isinstance(body, dict):
        return body
    if isinstance(body, (bytes, bytearray)):
        body = body.decode("utf-8", errors="ignore")
    if not isinstance(body, str):
        body = str(body)
    body = body.strip()
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        parsed = parse_qs(body, keep_blank_values=True)
        return {
            key: value[0] if len(value) == 1 else value
            for key, value in parsed.items()
        }


def _parse_cookie_header(cookie_header):
    cookies = {}
    if not cookie_header:
        return cookies
    for item in cookie_header.split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def _make_cookie(session_id, max_age=SESSION_TTL_SECONDS):
    return (
        f"{SESSION_COOKIE_NAME}={session_id}; "
        f"Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}"
    )


def _clear_cookie():
    return f"{SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


def _response(body, status_code=200, headers=None):
    return {
        "status_code": status_code,
        "headers": headers or {},
        "body": body,
    }


def _create_session(username):
    session_id = secrets.token_hex(16)
    with SESSIONS_LOCK:
        SESSIONS[session_id] = {
            "username": username,
            "expires_at": time.time() + SESSION_TTL_SECONDS,
        }
    return session_id


def _read_session(headers):
    normalized_headers = _normalize_headers(headers)
    cookies = _parse_cookie_header(normalized_headers.get("cookie", ""))
    session_id = cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None, None

    with SESSIONS_LOCK:
        session = SESSIONS.get(session_id)
        if not session:
            return session_id, None
        if session["expires_at"] < time.time():
            del SESSIONS[session_id]
            return session_id, None
        return session_id, session


def _require_login(headers):
    _, session = _read_session(headers)
    if not session:
        return False, None, _response(
            {"ok": False, "message": "Unauthorized. Please login first."},
            status_code=401,
        )
    return True, session["username"], None


def _append_message(sender, message, channel="general", direction="in"):
    item = {
        "sender": sender,
        "message": message,
        "channel": channel,
        "direction": direction,
        "timestamp": time.time(),
    }
    with HISTORY_LOCK:
        CHAT_HISTORY.append(item)
    return item


def _active_peers_locked():
    now = time.time()
    return {
        peer_id: dict(peer)
        for peer_id, peer in PEERS.items()
        if now - peer.get("last_seen", 0) <= PEER_TIMEOUT
    }


def _send_peer_worker(target_ip, target_port, message, sender, channel="general"):
    url = f"http://{target_ip}:{int(target_port)}/receive-message"
    payload = json.dumps(
        {"message": message, "sender": sender, "channel": channel}
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            ok = 200 <= response.status < 300
            print(f"[P2P] send {sender} -> {target_ip}:{target_port} ok={ok}")
            return ok, None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"[P2P] send failed to {target_ip}:{target_port}: {exc}")
        return False, str(exc)


@route("/login", ["POST", "PUT"])
def login(headers="guest", body="anonymous"):
    payload = _parse_body(body)
    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    if USERS.get(username) != password:
        return _response(
            {"ok": False, "message": "Invalid username or password"},
            status_code=401,
        )

    session_id = _create_session(username)
    return _response(
        {"ok": True, "message": "Login successful", "username": username},
        headers={"Set-Cookie": _make_cookie(session_id)},
    )


@route("/logout", ["POST"])
def logout(headers="guest", body="anonymous"):
    session_id, session = _read_session(headers)
    with SESSIONS_LOCK:
        if session_id in SESSIONS:
            del SESSIONS[session_id]
    return _response(
        {"ok": True, "message": "Logged out", "had_session": session is not None},
        headers={"Set-Cookie": _clear_cookie()},
    )


@route("/me", ["GET"])
def me(headers="guest", body="anonymous"):
    ok, username, error = _require_login(headers)
    if not ok:
        return error
    return _response({"ok": True, "username": username})


@route("/hello", ["POST", "PUT"])
async def hello(headers="guest", body="anonymous"):
    ok, username, error = _require_login(headers)
    if not ok:
        return error
    payload = _parse_body(body)
    message = payload.get("message", "Hello")
    return _response({"ok": True, "message": f"{message}, {username}!"})


@route("/submit-info", ["POST"])
def submit_info(headers="guest", body="anonymous"):
    ok, username, error = _require_login(headers)
    if not ok:
        return error

    payload = _parse_body(body)
    peer_id = str(payload.get("peer_id") or username)
    ip = payload.get("ip")
    raw_port = payload.get("port")
    if not ip or raw_port is None:
        return _response({"ok": False, "message": "Missing ip or port"}, status_code=400)

    try:
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError
    except (TypeError, ValueError):
        return _response({"ok": False, "message": "Invalid port number"}, status_code=400)

    with TRACKER_LOCK:
        existing = PEERS.get(peer_id, {})
        PEERS[peer_id] = {
            "ip": str(ip),
            "port": port,
            "channels": existing.get("channels", []),
            "status": "online",
            "last_seen": time.time(),
            "owner": username,
        }

    return _response({"ok": True, "message": "Peer registered", "peer_id": peer_id})


@route("/add-list", ["POST"])
def add_list(headers="guest", body="anonymous"):
    ok, username, error = _require_login(headers)
    if not ok:
        return error

    payload = _parse_body(body)
    peer_id = str(payload.get("peer_id") or username)
    channel = str(payload.get("channel") or "general")

    with TRACKER_LOCK:
        if peer_id not in PEERS:
            return _response(
                {"ok": False, "message": "Peer is not registered"},
                status_code=404,
            )
        CHANNELS.setdefault(channel, set()).add(peer_id)
        if channel not in PEERS[peer_id]["channels"]:
            PEERS[peer_id]["channels"].append(channel)
        PEERS[peer_id]["last_seen"] = time.time()

    return _response({"ok": True, "message": f"Joined channel {channel}"})


@route("/get-list", ["GET", "POST"])
def get_list(headers="guest", body="anonymous"):
    ok, _, error = _require_login(headers)
    if not ok:
        return error

    with TRACKER_LOCK:
        active_peers = _active_peers_locked()
        channels = {
            channel: sorted(peer_id for peer_id in members if peer_id in active_peers)
            for channel, members in CHANNELS.items()
        }

    return _response({"ok": True, "peers": active_peers, "channels": channels})


@route("/connect-peer", ["POST"])
def connect_peer(headers="guest", body="anonymous"):
    ok, _, error = _require_login(headers)
    if not ok:
        return error

    payload = _parse_body(body)
    target_id = str(payload.get("target_peer_id") or "")
    if not target_id:
        return _response({"ok": False, "message": "Missing target_peer_id"}, status_code=400)

    with TRACKER_LOCK:
        active_peers = _active_peers_locked()
        peer = active_peers.get(target_id)

    if not peer:
        return _response({"ok": False, "message": "Peer not found or offline"}, status_code=404)
    return _response({"ok": True, "target_peer_id": target_id, **peer})


@route("/send-peer", ["POST"])
def send_peer(headers="guest", body="anonymous"):
    ok, username, error = _require_login(headers)
    if not ok:
        return error

    payload = _parse_body(body)
    target_ip = payload.get("target_ip")
    target_port = payload.get("target_port")
    message = payload.get("message")
    channel = payload.get("channel", "general")
    if not all([target_ip, target_port, message]):
        return _response(
            {"ok": False, "message": "Missing target_ip, target_port, or message"},
            status_code=400,
        )

    _append_message("Me", message, channel=channel, direction="out")
    thread = threading.Thread(
        target=_send_peer_worker,
        args=(target_ip, target_port, message, username, channel),
        daemon=True,
    )
    thread.start()
    return _response({"ok": True, "message": "Message queued for P2P sending"})


@route("/broadcast-peer", ["POST"])
def broadcast_peer(headers="guest", body="anonymous"):
    ok, username, error = _require_login(headers)
    if not ok:
        return error

    payload = _parse_body(body)
    message = payload.get("message")
    channel = payload.get("channel", "general")
    own_peer_id = str(payload.get("peer_id") or username)
    peers = payload.get("peers")

    if not message:
        return _response({"ok": False, "message": "Missing message"}, status_code=400)

    if not peers:
        with TRACKER_LOCK:
            active_peers = _active_peers_locked()
            peers = [
                peer for peer_id, peer in active_peers.items()
                if peer_id != own_peer_id
            ]

    queued = []
    for peer in peers:
        target_ip = peer.get("ip")
        target_port = peer.get("port")
        if not target_ip or not target_port:
            queued.append({"peer": peer, "queued": False, "error": "Missing ip or port"})
            continue
        thread = threading.Thread(
            target=_send_peer_worker,
            args=(target_ip, target_port, message, username, channel),
            daemon=True,
        )
        thread.start()
        queued.append({"peer": peer, "queued": True})

    _append_message("Me", message, channel=channel, direction="out")
    return _response({"ok": True, "message": "Broadcast queued", "results": queued})


@route("/receive-message", ["POST"])
def receive_message(headers="guest", body="anonymous"):
    payload = _parse_body(body)
    message = payload.get("message")
    sender = payload.get("sender", "unknown")
    channel = payload.get("channel", "general")
    if not message:
        return _response({"ok": False, "message": "No message provided"}, status_code=400)

    _append_message(sender, message, channel=channel, direction="in")
    return _response({"ok": True, "message": "Message received"})


@route("/poll-messages", ["GET"])
def poll_messages(headers="guest", body="anonymous"):
    ok, _, error = _require_login(headers)
    if not ok:
        return error
    with HISTORY_LOCK:
        messages = list(CHAT_HISTORY)
    return _response({"ok": True, "messages": messages})


def create_sampleapp(ip, port):
    app.prepare_address(ip, port)
    app.run()
