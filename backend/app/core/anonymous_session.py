"""Anonymous browser credentials; only their hashes are stored with analyses."""

import hashlib
import re
import secrets

from fastapi import HTTPException, Request, Response

COOKIE_NAME = "sonar_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 365


def session_owner(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME, "")
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        raise HTTPException(401, "Initialize an anonymous browser session first.")
    return hashlib.sha256(token.encode()).hexdigest()


def initialize_session(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME, "")
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        token = secrets.token_hex(32)
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_MAX_AGE, httponly=True,
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
        samesite="lax", path="/api",
    )
    response.headers["Cache-Control"] = "private, no-store"
    return {"status": "ready"}
