"""Auth GUI local con login/registro estándar de usuario y contraseña."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from io import BytesIO

import pytest

from core.http_auth import ConfiguredBearerAuth, HttpAuthInvalidCredentials, HttpAuthPrincipalExists
from ingestion.gui.auth_session import SESSION_COOKIE_NAME, GuiAuthCoordinator, GuiSessionStore, parse_cookie
from ingestion.gui.local_operator_auth import LocalOperatorDirectory
import ingestion.gui.server as gui_server_module
from ingestion.gui.server import Phase1GuiHandler

_PASSWORD = "Clave123!"
_T0 = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def _directory(tmp_path) -> LocalOperatorDirectory:
    return LocalOperatorDirectory(tmp_path / "gui_auth_users.json")


def _coordinator(tmp_path) -> GuiAuthCoordinator:
    directory = _directory(tmp_path)
    directory.register(username="op-1", password=_PASSWORD)
    return GuiAuthCoordinator(
        authenticator=ConfiguredBearerAuth({}),
        store=GuiSessionStore(),
        directory=directory,
    )


def _empty_coordinator(tmp_path) -> GuiAuthCoordinator:
    return GuiAuthCoordinator(
        authenticator=ConfiguredBearerAuth({}),
        store=GuiSessionStore(),
        directory=_directory(tmp_path),
    )


def test_store_resuelve_sesion_viva_y_purga_expirada() -> None:
    store = GuiSessionStore(ttl_seconds=3600)
    session = store.create(
        principal_id="op-1",
        project_scope=None,
        bearer_credential="internal-token",
        now=_T0,
    )

    assert store.resolve(session.session_id, now=_T0).session_id == session.session_id
    assert store.resolve(session.session_id, now=_T0 + timedelta(hours=2)) is None
    assert store.resolve(session.session_id, now=_T0) is None


def test_store_revoke_elimina_la_sesion() -> None:
    store = GuiSessionStore()
    session = store.create(
        principal_id="op-1",
        project_scope=None,
        bearer_credential="internal-token",
        now=_T0,
    )
    store.revoke(session.session_id)
    assert store.resolve(session.session_id, now=_T0) is None


def test_parse_cookie_extrae_valor_por_nombre() -> None:
    header = f"other=1; {SESSION_COOKIE_NAME}=abc123; last=z"
    assert parse_cookie(header, SESSION_COOKIE_NAME) == "abc123"
    assert parse_cookie(None, SESSION_COOKIE_NAME) is None
    assert parse_cookie("nope=1", SESSION_COOKIE_NAME) is None


def test_register_y_login_crean_sesion_cuando_credenciales_son_validas(tmp_path) -> None:
    coordinator = _empty_coordinator(tmp_path)

    registration = coordinator.register(
        username="nuevo-operador",
        password=_PASSWORD,
        now=_T0,
    )
    replay = coordinator.login(username="nuevo-operador", password=_PASSWORD, now=_T0)

    assert registration.principal_id == "nuevo-operador"
    assert registration.project_scope is None
    assert replay.principal_id == "nuevo-operador"
    assert replay.project_scope is None


def test_register_con_scope_lo_propaga_a_la_sesion_y_persiste_en_login(tmp_path) -> None:
    coordinator = _empty_coordinator(tmp_path)

    registration = coordinator.register(
        username="op-scoped",
        password=_PASSWORD,
        project_scope=("proj_b", "proj_a", "proj_a"),
        now=_T0,
    )
    replay = coordinator.login(username="op-scoped", password=_PASSWORD, now=_T0)

    # El scope se normaliza (dedupe + orden estable) y sobrevive al re-login.
    assert registration.project_scope == ("proj_a", "proj_b")
    assert replay.project_scope == ("proj_a", "proj_b")


def test_register_falla_cerrado_cuando_usuario_esta_duplicado(tmp_path) -> None:
    coordinator = _empty_coordinator(tmp_path)
    coordinator.register(username="nuevo-operador", password=_PASSWORD, now=_T0)

    with pytest.raises(HttpAuthPrincipalExists):
        coordinator.register(username="nuevo-operador", password=_PASSWORD, now=_T0)


def test_login_falla_cerrado_cuando_contrasena_es_invalida(tmp_path) -> None:
    coordinator = _coordinator(tmp_path)

    with pytest.raises(HttpAuthInvalidCredentials):
        coordinator.login(username="op-1", password="otra-clave", now=_T0)


def test_directorio_rehidrata_usuario_despues_de_reinicio(tmp_path) -> None:
    registry_path = tmp_path / "gui_auth_users.json"
    directory = LocalOperatorDirectory(registry_path)
    directory.register(username="nuevo-operador", password=_PASSWORD)

    restarted = LocalOperatorDirectory(registry_path)
    account = restarted.authenticate(username="nuevo-operador", password=_PASSWORD)

    assert account.username == "nuevo-operador"


def test_directorio_no_guarda_contrasena_en_claro(tmp_path) -> None:
    registry_path = tmp_path / "gui_auth_users.json"
    directory = LocalOperatorDirectory(registry_path)
    directory.register(username="nuevo-operador", password=_PASSWORD)

    payload = registry_path.read_text(encoding="utf-8")

    assert "nuevo-operador" in payload
    assert _PASSWORD not in payload


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


def test_register_handler_crea_usuario_y_pone_cookie(tmp_path) -> None:
    body = _body_bytes({"username": "nuevo-operador", "password": _PASSWORD})
    handler = _make_handler(
        path="/api/auth/register",
        headers={"Content-Length": str(len(body))},
        body=body,
        coordinator=_empty_coordinator(tmp_path),
    )

    handler._handle_auth_register()

    assert handler._response_status_code == HTTPStatus.OK
    cookie = handler.sent_headers["Set-Cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    payload = json.loads(handler.wfile.getvalue())
    assert payload == {
        "authenticated": True,
        "principal_id": "nuevo-operador",
        "project_scope": None,
    }


def test_register_handler_acepta_project_scope_del_body(tmp_path) -> None:
    body = _body_bytes(
        {
            "username": "op-scoped",
            "password": _PASSWORD,
            "project_scope": ["proj_b", "proj_a"],
        }
    )
    handler = _make_handler(
        path="/api/auth/register",
        headers={"Content-Length": str(len(body))},
        body=body,
        coordinator=_empty_coordinator(tmp_path),
    )

    handler._handle_auth_register()

    assert handler._response_status_code == HTTPStatus.OK
    payload = json.loads(handler.wfile.getvalue())
    assert payload["project_scope"] == ["proj_a", "proj_b"]


def test_register_handler_rechaza_project_scope_mal_formado(tmp_path) -> None:
    body = _body_bytes(
        {"username": "op-x", "password": _PASSWORD, "project_scope": "proj_a"}
    )
    handler = _make_handler(
        path="/api/auth/register",
        headers={"Content-Length": str(len(body))},
        body=body,
        coordinator=_empty_coordinator(tmp_path),
    )

    handler._handle_auth_register()

    assert handler._response_status_code == HTTPStatus.BAD_REQUEST


def test_login_handler_autentica_con_usuario_y_contrasena(tmp_path) -> None:
    body = _body_bytes({"username": "op-1", "password": _PASSWORD})
    handler = _make_handler(
        path="/api/auth/login",
        headers={"Content-Length": str(len(body))},
        body=body,
        coordinator=_coordinator(tmp_path),
    )

    handler._handle_auth_login()

    assert handler._response_status_code == HTTPStatus.OK
    payload = json.loads(handler.wfile.getvalue())
    assert payload == {
        "authenticated": True,
        "principal_id": "op-1",
        "project_scope": None,
    }


def test_login_handler_falla_cuando_contrasena_es_invalida(tmp_path) -> None:
    body = _body_bytes({"username": "op-1", "password": "otra-clave"})
    handler = _make_handler(
        path="/api/auth/login",
        headers={"Content-Length": str(len(body))},
        body=body,
        coordinator=_coordinator(tmp_path),
    )

    handler._handle_auth_login()

    assert handler._response_status_code == HTTPStatus.UNAUTHORIZED
    assert "Set-Cookie" not in handler.sent_headers


def test_session_handler_con_cookie_valida_devuelve_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(gui_server_module, "_utcnow", lambda: _T0)
    coordinator = _coordinator(tmp_path)
    session = coordinator.login(username="op-1", password=_PASSWORD, now=_T0)
    handler = _make_handler(
        path="/api/auth/session",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={session.session_id}"},
        coordinator=coordinator,
    )

    handler._handle_auth_session()

    assert handler._response_status_code == HTTPStatus.OK
    assert json.loads(handler.wfile.getvalue()) == {
        "authenticated": True,
        "principal_id": "op-1",
        "project_scope": None,
    }


def test_logout_handler_revoca_la_sesion(tmp_path) -> None:
    coordinator = _coordinator(tmp_path)
    session = coordinator.login(username="op-1", password=_PASSWORD, now=_T0)
    handler = _make_handler(
        path="/api/auth/logout",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={session.session_id}"},
        coordinator=coordinator,
    )

    handler._handle_auth_logout()

    assert handler._response_status_code == HTTPStatus.OK
    assert "Max-Age=0" in handler.sent_headers["Set-Cookie"]
    assert coordinator.resolve(session.session_id, now=_T0) is None


def test_platform_con_cookie_valida_inyecta_bearer_server_side(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(gui_server_module, "_utcnow", lambda: _T0)
    coordinator = _coordinator(tmp_path)
    session = coordinator.login(username="op-1", password=_PASSWORD, now=_T0)
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
    assert forwarded["Authorization"].startswith("Bearer ")
    assert forwarded["Authorization"] != "Bearer cliente-no-confiable"


def test_platform_con_cookie_invalida_falla_cerrado(tmp_path) -> None:
    bridge = _RecordingBridge(_BridgeResponse(200, b"{}"))
    handler = _make_handler(
        path="/api/platform/projects",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}=no-existe"},
        coordinator=_coordinator(tmp_path),
        bridge=bridge,
    )

    handler._handle_pipeline_api("GET")

    assert handler._response_status_code == HTTPStatus.UNAUTHORIZED
    assert bridge.calls == []
