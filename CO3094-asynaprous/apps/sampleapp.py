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


def create_sampleapp(ip, port):
    app.prepare_address(ip, port)
    app.run()