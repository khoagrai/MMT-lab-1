# Copyright (C) 2026 pdnguyen of HCMC University of Technology VNU-HCM.
# All rights reserved.
# This file is part of the CO3093/CO3094 course,
# and is released under the "MIT License Agreement". Please see the LICENSE
# file that should have been included as part of this package.
#
# AsynapRous release
#
# The authors hereby grant to Licensee personal permission to use
# and modify the Licensed Source Code for the sole purpose of studying
# while attending the course
#
"""
app.sampleapp
~~~~~~~~~~~~~~~~~
"""

import json
import secrets
import time
import threading
from urllib.parse import parse_qs

from daemon import AsynapRous

app = AsynapRous()

USERS = {
    "admin": "123456",
    "khoi": "123456",
    "user1": "123456",
}

SESSION_COOKIE_NAME = "session_id"
SESSION_TTL_SECONDS = 3600
SESSIONS = {}


def _normalize_headers(headers):
    if headers is None:
        return {}

    if isinstance(headers, dict):
        return {str(k).lower(): str(v) for k, v in headers.items()}

    try:
        return {str(k).lower(): str(v) for k, v in dict(headers).items()}
    except Exception:
        return {}


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
    return (
        f"{SESSION_COOKIE_NAME}=; "
        f"Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
    )


def _response(body, status_code=200, headers=None):
    return {
        "status_code": status_code,
        "headers": headers or {},
        "body": body,
    }


def _create_session(username):
    session_id = secrets.token_hex(16)
    SESSIONS[session_id] = {
        "username": username,
        "expires_at": time.time() + SESSION_TTL_SECONDS,
    }
    return session_id


def _read_session(headers):
    normalized_headers = _normalize_headers(headers)
    cookie_header = normalized_headers.get("cookie", "")
    cookies = _parse_cookie_header(cookie_header)

    session_id = cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None, None

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
        return (
            False,
            None,
            _response(
                {
                    "ok": False,
                    "message": "Unauthorized. Please login first."
                },
                status_code=401,
            ),
        )

    return True, session["username"], None


@app.route("/login", methods=["POST", "PUT"])
def login(headers="guest", body="anonymous"):
    payload = _parse_body(body)
    username = payload.get("username", "")
    password = payload.get("password", "")

    print("[SampleApp] login payload={}".format(payload))

    if USERS.get(username) != password:
        return _response(
            {
                "ok": False,
                "message": "Invalid username or password",
            },
            status_code=401,
        )

    session_id = _create_session(username)

    return _response(
        {
            "ok": True,
            "message": "Login successful",
            "username": username,
        },
        status_code=200,
        headers={
            "Set-Cookie": _make_cookie(session_id),
        },
    )


@app.route("/logout", methods=["POST"])
def logout(headers="guest", body="anonymous"):
    session_id, session = _read_session(headers)

    if session_id and session_id in SESSIONS:
        del SESSIONS[session_id]

    return _response(
        {
            "ok": True,
            "message": "Logged out",
            "had_session": session is not None,
        },
        headers={
            "Set-Cookie": _clear_cookie(),
        },
    )


@app.route("/me", methods=["GET"])
def me(headers="guest", body="anonymous"):
    ok, username, error_response = _require_login(headers)
    if not ok:
        return error_response

    return _response(
        {
            "ok": True,
            "username": username,
        }
    )


@app.route("/echo", methods=["POST"])
def echo(headers="guest", body="anonymous"):
    print("[SampleApp] received body {}".format(body))
    payload = _parse_body(body)

    return _response(
        {
            "ok": True,
            "received": payload,
        }
    )


@app.route("/hello", methods=["POST", "PUT"])
async def hello(headers="guest", body="anonymous"):
    ok, username, error_response = _require_login(headers)
    if not ok:
        return error_response

    payload = _parse_body(body)
    message = payload.get("message", "Hello")

    print("[SampleApp] protected hello user={} body={}".format(username, payload))

    return _response(
        {
            "ok": True,
            "message": f"{message}, {username}!",
        }
    )

PEERS = {}
CHANNELS = {}
TRACKER_LOCK = threading.Lock()
PEER_TIMEOUT = 60

@app.route("/submit-info", methods=["POST"])
def submit_info(headers="guest", body="anonymous"):
    payload = _parse_body(body)
    if not isinstance(payload, dict):
        payload = {}
    peer_id = payload.get("peer_id")
    ip = payload.get("ip")
    raw_port = payload.get("port")
    
    if not peer_id or not ip or raw_port is None:
        return _response(
            {"ok": False, "message": "Missing peer_id, ip, or port"},
            status_code=400,
        )
        
    try:
        port = int(raw_port)
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        return _response(
            {"ok": False, "message": "Invalid port number. Must be 1-65535."},
            status_code=400,
        )
        
    peer_id = str(peer_id)
    
    with TRACKER_LOCK:
        existing_channels = PEERS.get(peer_id, {}).get("channels", [])
        PEERS[peer_id] = {
            "ip": ip,
            "port": port,
            "channels": existing_channels,
            "status": "online",
            "last_seen": time.time(),
        }

    print("[Tracker] Peer registered/updated: {} at {}:{}".format(peer_id, ip, port))
    return _response(
        {
            "ok": True,
            "message": "Peer info submitted successfully",
            "peer_id": peer_id,
        }
    )

@app.route("/add-list", methods=["POST"])
def add_list(headers="guest", body="anonymous"):
    payload = _parse_body(body)
    if not isinstance(payload, dict):
        payload = {}
    peer_id = payload.get("peer_id")
    channel = payload.get("channel")

    if not peer_id or not channel:
        return _response(
            {"ok": False, "message": "Missing peer_id or channel"},
            status_code=400,
        )
        
    peer_id = str(peer_id)
    channel = str(channel)

    with TRACKER_LOCK:
        if peer_id not in PEERS:
            return _response(
                {"ok": False, "message": "Peer {} not registered.".format(peer_id)},
                status_code=404,
            )

        if channel not in CHANNELS:
            CHANNELS[channel] = set()
        CHANNELS[channel].add(peer_id)

        if channel not in PEERS[peer_id]["channels"]:
            PEERS[peer_id]["channels"].append(channel)
            
        PEERS[peer_id]["last_seen"] = time.time()

    print("[Tracker] Peer {} joined channel {}".format(peer_id, channel))
    return _response(
        {
            "ok": True,
            "message": "Added to channel {}".format(channel),
        }
    )

@app.route("/get-list", methods=["GET", "POST"])
def get_list(headers="guest", body="anonymous"):
    current_time = time.time()
    with TRACKER_LOCK:
        active_peers = {
            pid: pinfo for pid, pinfo in PEERS.items()
            if (current_time - pinfo["last_seen"]) <= PEER_TIMEOUT
        }
        
        serializable_channels = {}
        for ch, members in CHANNELS.items():
            active_members = [m for m in members if m in active_peers]
            serializable_channels[ch] = sorted(active_members)
            
    return _response(
        {
            "ok": True,
            "peers": active_peers,
            "channels": serializable_channels,
        }
    )

@app.route("/connect-peer", methods=["POST"])
def connect_peer(headers="guest", body="anonymous"):
    payload = _parse_body(body)
    if not isinstance(payload, dict):
        payload = {}
    target_id = payload.get("target_peer_id")

    if not target_id:
        return _response(
            {"ok": False, "message": "Missing target_peer_id"},
            status_code=400,
        )

    target_id = str(target_id)
    
    with TRACKER_LOCK:
        target_peer = PEERS.get(target_id)
        if not target_peer or (time.time() - target_peer["last_seen"] > PEER_TIMEOUT):
            return _response(
                {"ok": False, "message": "Peer not found or offline"},
                status_code=404,
            )
        ip = target_peer["ip"]
        port = target_peer["port"]

    return _response(
        {
            "ok": True,
            "target_peer_id": target_id,
            "ip": ip,
            "port": port,
        }
    )

def create_sampleapp(ip, port):
    app.prepare_address(ip, port)
    app.run()
