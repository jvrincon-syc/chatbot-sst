"""Sesión GUI local por cookie opaca (Gate 3, Fase 8).

PENDIENTE DE EJECUCIÓN por el operador.

Cubre el store en memoria (TTL/revoke/purge), el coordinador (login valida con la
misma autoridad que FastAPI) y el handler del bridge:

- ``POST /api/auth/login`` valida token, abre sesión y pone cookie HttpOnly;
- ``GET /api/auth/session`` devuelve metadata pública o 401;
- ``POST /api/auth/logout`` revoca y expira la cookie;
- ``/api/platform/*`` con cookie válida → inyecta bearer server-side y descarta
  el Authorization del cliente; cookie inválida → 401; sin cookie → passthrough.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from io import BytesIO

import pytest

from core.http_auth import (
    AUTH_CREDENTIALS_JSON_KEY,
    ConfiguredBearerAuth,
    HttpAuthInvalidCredentials,
    HttpAuthNotConfigured,
)
from ingestion.gui.auth_session import (
    SESSION_COOKIE_NAME,
    GuiAuthCoordinator,
    GuiSessionStore,
    parse_cookie,
)
from ingestion.gui.server import Phase1GuiHandler

_TOKEN = "tok-123"
_T0 = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def _authenticator() -> ConfiguredBearerAuth:
    return ConfiguredBearerAuth(
        {
            AUTH_CREDENTIALS_JSON_KEY: json.dumps(
                [
                    {
                        "principal_id": "op-1",
                        "token": _TOKEN,
                        "project_scope": ["proj_alpha"],
                    }
                ]
            )
        }
    )


def _coordinator() -> GuiAuthCoordinator:
    return GuiAuthCoordinator(
        authenticator=_authenticator(), store=GuiSessionStore()
    )


# --------------------------------------------------------------------------- #
# Store                                                                        #
# --------------------------------------------------------------------------- #


def test_store_resuelve_sesion_viva_y_purga_expirada() -> None:
    store = GuiSessionStore(ttl_seconds=3600)
    session = store.create(
        principal_id="op-1",
        project_scope=("proj_alpha",),
        bearer_credential=_TOKEN,
        now=_T0,
    )

    assert store.resolve(session.session_id, now=_T0).session_id == session.session_id
    # Expirada: no resuelve y queda purgada (fail-closed).
    assert store.resolve(session.session_id, now=_T0 + timedelta(hours=2)) is None
    assert store.resolve(session.session_id, now=_T0) is None


def test_store_revoke_elimina_la_sesion() -> None:
    store = GuiSessionStore()
    session = store.create(
        principal_id="op-1", project_scope=None, bearer_credential=_TOKEN, now=_T0
    )
    store.revoke(session.session_id)
    assert store.resolve(session.session_id, now=_T0) is None


def test_parse_cookie_extrae_valor_por_nombre() -> None:
    header = f"other=1; {SESSION_COOKIE_NAME}=abc123; last=z"
    assert parse_cookie(header, SESSION_COOKIE_NAME) == "abc123"
    assert parse_cookie(None, SESSION_COOKIE_NAME) is None
    assert parse_cookie("nope=1", SESSION_COOKIE_NAME) is None


# --------------------------------------------------------------------------- #
# Coordinador                                                                  #
# --------------------------------------------------------------------------- #


def test_login_valido_crea_sesion_con_scope() -> None:
    session = _coordinator().login(_TOKEN, now=_T0)
    assert session.principal_id == "op-1"
    assert session.project_scope == ("proj_alpha",)
    assert session.bearer_credential == _TOKEN


def test_login_token_invalido_falla_cerrado() -> None:
    with pytest.raises(HttpAuthInvalidCredentials):
        _coordinator().login("tok-malo", now=_T0)


def test_login_sin_credenciales_configuradas_falla_cerrado() -> None:
    coordinator = GuiAuthCoordinator(
        authenticator=ConfiguredBearerAuth({}), store=GuiSessionStore()
    )
    with pytest.raises(HttpAuthNotConfigured):
        coordinator.login(_TOKEN, now=_T0)


# --------------------------------------------------------------------------- #
# Handler (bridge)                                                             #
# --------------------------------------------------------------------------- #


class _BridgeResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body
        self.headers = {"content-type": "application/json"}


class _RecordingBridge:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def handle(self, *, method, path, headers, body):
        self.calls.append({"method": method, "path": path, "headers": headers, "body": body})
        return self._response


def _make_handler(*, path, headers, body=b"", coordinator=None, bridge=None):
    handler = Phase1GuiHandler.__new__(Phase1GuiHandler)
    handler.path = path
    handler.headers = dict(headers)
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    handler.client_address = None
    handler._response_status_code = None
    handler.sent_headers = {}
    handler.send_response = lambda status, *a: None
    handler.send_header = lambda name, value: handler.sent_headers.__setitem__(name, value)
    handler.end_headers = lambda: None

    class _Server:
        pass

    server = _Server()
    server.gui_auth = coordinator
    server.pipeline_api = bridge
    handler.server = server
    return handler


def _body_bytes(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_login_handler_pone_cookie_y_devuelve_metadata() -> None:
    coordinator = _coordinator()
    body = _body_bytes({"token": _TOKEN})
    handler = _make_handler(
        path="/api/auth/login",
        headers={"Content-Length": str(len(body))},
        body=body,
        coordinator=coordinator,
    )
    handler._handle_auth_login()

    assert handler._response_status_code == HTTPStatus.OK
    cookie = handler.sent_headers["Set-Cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    payload = json.loads(handler.wfile.getvalue())
    assert payload == {
        "authenticated": True,
        "principal_id": "op-1",
        "project_scope": ["proj_alpha"],
    }


def test_login_handler_token_invalido_da_401() -> None:
    handler = _make_handler(
        path="/api/auth/login",
        headers={"Content-Length": "20"},
        body=_body_bytes({"token": "malo"}),
        coordinator=_coordinator(),
    )
    handler._handle_auth_login()
    assert handler._response_status_code == HTTPStatus.UNAUTHORIZED
    assert "Set-Cookie" not in handler.sent_headers


def test_login_handler_origen_no_confiable_da_403() -> None:
    body = _body_bytes({"token": _TOKEN})
    handler = _make_handler(
        path="/api/auth/login",
        headers={"Content-Length": str(len(body)), "Origin": "http://evil.example"},
        body=body,
        coordinator=_coordinator(),
    )
    handler._handle_auth_login()
    assert handler._response_status_code == HTTPStatus.FORBIDDEN


def test_session_handler_sin_cookie_da_401() -> None:
    handler = _make_handler(
        path="/api/auth/session", headers={}, coordinator=_coordinator()
    )
    handler._handle_auth_session()
    assert handler._response_status_code == HTTPStatus.UNAUTHORIZED
    assert json.loads(handler.wfile.getvalue()) == {"authenticated": False}


def test_session_handler_con_cookie_valida_da_metadata() -> None:
    coordinator = _coordinator()
    session = coordinator.login(_TOKEN, now=datetime.now(timezone.utc))
    handler = _make_handler(
        path="/api/auth/session",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={session.session_id}"},
        coordinator=coordinator,
    )
    handler._handle_auth_session()
    assert handler._response_status_code == HTTPStatus.OK
    assert json.loads(handler.wfile.getvalue())["principal_id"] == "op-1"


def test_logout_handler_revoca_y_expira_cookie() -> None:
    coordinator = _coordinator()
    session = coordinator.login(_TOKEN, now=datetime.now(timezone.utc))
    handler = _make_handler(
        path="/api/auth/logout",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={session.session_id}"},
        coordinator=coordinator,
    )
    handler._handle_auth_logout()
    assert handler._response_status_code == HTTPStatus.OK
    assert "Max-Age=0" in handler.sent_headers["Set-Cookie"]
    # Sesión revocada: ya no resuelve.
    assert coordinator.resolve(session.session_id, now=datetime.now(timezone.utc)) is None


# --------------------------------------------------------------------------- #
# Inyección de bearer en /api/platform/*                                       #
# --------------------------------------------------------------------------- #


def test_platform_con_cookie_valida_inyecta_bearer_y_descarta_authorization() -> None:
    coordinator = _coordinator()
    session = coordinator.login(_TOKEN, now=datetime.now(timezone.utc))
    bridge = _RecordingBridge(_BridgeResponse(200, b"{}"))
    handler = _make_handler(
        path="/api/platform/projects",
        headers={
            "Cookie": f"{SESSION_COOKIE_NAME}={session.session_id}",
            "Authorization": "Bearer cliente-no-confiable",
        },
        coordinator=coordinator,
        bridge=bridge,
    )
    handler._handle_pipeline_api("GET")

    forwarded = bridge.calls[0]["headers"]
    assert forwarded["Authorization"] == f"Bearer {_TOKEN}"


def test_platform_con_cookie_invalida_da_401_y_no_reenvia() -> None:
    bridge = _RecordingBridge(_BridgeResponse(200, b"{}"))
    handler = _make_handler(
        path="/api/platform/projects",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}=no-existe"},
        coordinator=_coordinator(),
        bridge=bridge,
    )
    handler._handle_pipeline_api("GET")

    assert handler._response_status_code == HTTPStatus.UNAUTHORIZED
    assert bridge.calls == []


def test_platform_sin_cookie_reenvia_authorization_tal_cual() -> None:
    bridge = _RecordingBridge(_BridgeResponse(200, b"{}"))
    handler = _make_handler(
        path="/api/platform/projects",
        headers={"Authorization": "Bearer directo"},
        coordinator=_coordinator(),
        bridge=bridge,
    )
    handler._handle_pipeline_api("GET")

    forwarded = bridge.calls[0]["headers"]
    assert forwarded["Authorization"] == "Bearer directo"
