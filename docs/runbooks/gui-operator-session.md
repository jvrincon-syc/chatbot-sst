# GUI Operator Session Runbook

## Scope

Cómo configurar, arrancar y operar la **GUI de plataforma RAG** (Fase 8) con su
sesión local de operador. No cambia la lógica de negocio ni los manifests
durables. La autorización sigue siendo responsabilidad de FastAPI (Fase 7): la
GUI solo pone una cookie de sesión delante del bearer existente.

## Modelo de sesión (Gate 3)

El browser nunca guarda el bearer. El flujo es:

```text
browser → POST /api/auth/login { token }   (una vez)
        → el backend GUI valida el token con ConfiguredBearerAuth
        → cookie HttpOnly opaca:  chatbot_sst_gui_session
        → el bearer queda en memoria server-side del bridge
/api/platform/* → el bridge inyecta Authorization: Bearer ... server-side
```

- Cookie: `chatbot_sst_gui_session` — `HttpOnly; SameSite=Strict; Path=/`
  (`Secure` cuando el servicio corra sobre HTTPS).
- TTL de sesión por defecto: **12 horas** (`DEFAULT_SESSION_TTL_SECONDS`); tras
  expirar, cualquier `/api/platform/*` responde `401 GUI_SESSION_REQUIRED` y la
  GUI vuelve a la pantalla de credencial.
- Logout: `POST /api/auth/logout` revoca la sesión y expira la cookie.
- Ningún log contiene el token ni el session id completo.

## Configuración previa

Variables de entorno del proceso backend (no van al frontend):

- `SST_HTTP_AUTH_CREDENTIALS_JSON` — registro de credenciales bearer estáticas
  (Fase 7). Es el token que el operador pega en el login.
- `SST_FEATURE_RAG_PLATFORM_V1` — debe estar habilitado para exponer
  `/api/platform/*` (default `False`).
- Modo PostgreSQL para el flujo real de release (memoria sirve para smoke).

> No leer ni copiar `secrets.env`. Usar `secrets.example.env` como plantilla.

## Arrancar la GUI

```powershell
# Backend GUI (bridge + FastAPI) y frontend Vite juntos:
npm run gui:dev

# O por separado:
npm run gui:api      # backend en :8765
npm run gui:front    # frontend Vite en 127.0.0.1:5173
```

## Login del operador

1. Abrir el frontend (`http://127.0.0.1:5173`).
2. En la pantalla de credencial, pegar el token del registro bearer.
3. La sesión queda activa (cookie); el rail muestra las superficies
   **Platform** y **Legacy pipeline**.

## Flujo E2E de aceptación (Platform)

```text
login
→ crear/seleccionar proyecto        (Projects)
→ configurar proyecto               (Projects)
→ subir documento RAW → srev_       (Documents)
→ normalizar revisión por variante  (Documents)
→ crear/seleccionar variante        (Variants, celda reconfirmada de la matriz)
→ crear corpus snapshot             (Corpus)
→ crear DRAFT → build → validate → publish   (Releases)
→ refrescar el browser
→ proyecto/snapshot/release rehidratan; el Legacy pipeline sigue etiquetado aparte
```

## Estados fail-closed que verás (no son bugs)

| Código | Qué significa | Qué hacer |
| --- | --- | --- |
| `401 GUI_SESSION_REQUIRED` | sesión expirada/ausente | volver a hacer login |
| `503 HTTP_AUTH_NOT_CONFIGURED` | el servidor no tiene registro bearer | configurar `SST_HTTP_AUTH_CREDENTIALS_JSON` (no es un problema de login) |
| `403 PLATFORM_ACCESS_DENIED` | recurso fuera del `project_scope` | usar un proyecto dentro del scope; no es una lista vacía |
| `409 STALE_VARIANT_MATRIX_CELL` | la config avanzó | refrescar la matriz y reconfirmar la celda |
| `409 INVALID_RELEASE_TRANSITION` | el estado real cambió | la GUI refetchea la release; reintentar la transición válida |
| `409 IDEMPOTENCY_KEY_CONFLICT` | intención en conflicto | acción explícita del operador; la GUI **no** reintenta sola |
| `422 RELEASE_BUILD_TOO_LARGE` | snapshot excede el tope | reducir el snapshot |

## Notas de seguridad

- El frontend nunca envía `actor_id`, `indexing_target_id`, `target_bindings`,
  nombres de tabla ni rutas físicas. La `target_binding_key` es lógica.
- La GUI solo persiste IDs de navegación (`selectedProjectId`,
  `selectedRagVariantId`, `selectedCorpusSnapshotId`, `selectedRagReleaseId`) en
  `chatbot-sst.platform.preferences.v1`; nunca el bearer, la cookie ni
  idempotency keys. La persistencia legacy (`chatbot-sst.dashboard.preferences.v2`)
  queda intacta.
- Cuando exista SSO/OIDC se reemplaza el provider de sesión, no los workspaces.
