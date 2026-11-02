import secrets

from flask import abort, jsonify, request, session


CSRF_FIELD_NAME = "csrf_token"
CSRF_HEADER_NAMES = ("X-CSRFToken", "X-CSRF-Token")
SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS"))


def get_csrf_token():
    token = session.get(CSRF_FIELD_NAME)
    if not token:
        token = secrets.token_urlsafe(24)
        session[CSRF_FIELD_NAME] = token
    return token


def regenerate_csrf_token():
    token = secrets.token_urlsafe(24)
    session[CSRF_FIELD_NAME] = token
    return token


def _submitted_csrf_token():
    for header_name in CSRF_HEADER_NAMES:
        token = request.headers.get(header_name)
        if token:
            return token

    if request.is_json:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            token = payload.get(CSRF_FIELD_NAME)
            if isinstance(token, str):
                return token

    return request.form.get(CSRF_FIELD_NAME, "")


def csrf_valid():
    submitted = _submitted_csrf_token()
    expected = session.get(CSRF_FIELD_NAME, "")
    if not submitted or not expected:
        return False
    return secrets.compare_digest(submitted, expected)


def validate_csrf_request():
    if request.method in SAFE_METHODS:
        return None
    if csrf_valid():
        return None

    if request.path.startswith("/api/"):
        return jsonify({"error": "CSRF validation failed."}), 400
    return abort(400, description="CSRF validation failed.")
