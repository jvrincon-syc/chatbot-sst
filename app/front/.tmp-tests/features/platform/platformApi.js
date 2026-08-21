// Cliente HTTP tipado de la superficie de plataforma (Fase 8, Task 4).
//
// Adaptador delgado sobre el cliente compartido `shared/api`: mismas garantías
// (envelope de error único, `credentials: "same-origin"`, cero bearer/localStorage;
// la auth va por la cookie de sesión de Gate 3). Los tipos vienen del OpenAPI
// generado (`platformTypes`), nunca de contratos a mano. No hay lógica de negocio
// aquí: valida y autoriza FastAPI.
import { buildQuery, createIdempotencyKey, getJson, patchJson, postJson, postMultipart, } from "../../shared/api/apiClient.js";
const BASE = "/api/platform";
function pageQuery(params) {
    return buildQuery({ page: params?.page, page_size: params?.pageSize });
}
async function collectAllPages(fetchPage) {
    const items = [];
    let page = 1;
    // Cota dura por si el backend reportara total_pages inconsistente (fail-safe).
    for (let guard = 0; guard < 1000; guard += 1) {
        const response = await fetchPage({ page, pageSize: 100 });
        items.push(...response.items);
        if (page >= response.total_pages || response.items.length === 0) {
            break;
        }
        page += 1;
    }
    return items;
}
// Las mutaciones de release exigen `Idempotency-Key`. Se genera una por intento
// salvo que el caller reuse una para reintentar la MISMA operación (replay seguro).
function withIdempotency(options) {
    return { ...options, idempotencyKey: options?.idempotencyKey ?? createIdempotencyKey("platform") };
}
// --- Proyectos / configuración ------------------------------------------- //
export function listProjects(params, options) {
    return getJson(`${BASE}/projects${pageQuery(params)}`, options);
}
export function getProject(projectId, options) {
    return getJson(`${BASE}/projects/${projectId}`, options);
}
export function createProject(body, options) {
    return postJson(`${BASE}/projects`, body, options);
}
export function updateProject(projectId, body, options) {
    return patchJson(`${BASE}/projects/${projectId}`, body, options);
}
export function getConfiguration(projectId, options) {
    return getJson(`${BASE}/projects/${projectId}/configuration`, options);
}
export function updateConfiguration(projectId, body, options) {
    return patchJson(`${BASE}/projects/${projectId}/configuration`, body, options);
}
// --- Variantes ------------------------------------------------------------ //
export function getVariantMatrix(projectId, options) {
    return getJson(`${BASE}/projects/${projectId}/variant-matrix`, options);
}
export function listVariants(projectId, params, options) {
    return getJson(`${BASE}/projects/${projectId}/variants${pageQuery(params)}`, options);
}
// Mismo criterio que documents/corpus: las vistas de variantes operan sobre el
// listado completo del proyecto, nunca sobre la primera página (25 ítems).
export async function listAllVariants(projectId, options) {
    return collectAllPages((params) => listVariants(projectId, params, options));
}
export function createVariant(projectId, body, options) {
    return postJson(`${BASE}/projects/${projectId}/variants`, body, options);
}
// --- Documentos (list / upload / normalize) ------------------------------- //
export function listDocuments(projectId, params, options) {
    return getJson(`${BASE}/projects/${projectId}/documents${pageQuery(params)}`, options);
}
// El read-model paginado devuelve 25 por defecto; el operador necesita el corpus
// completo (p. ej. 55 documentos). Recorre todas las páginas al máximo permitido
// (MAX_PAGE_SIZE=100) y devuelve el listado plano.
export async function listAllDocuments(projectId, options) {
    return collectAllPages((params) => listDocuments(projectId, params, options));
}
export function uploadDocument(projectId, file, sourceRelpath, options) {
    const form = new FormData();
    form.append("file", file);
    form.append("source_relpath", sourceRelpath);
    return postMultipart(`${BASE}/projects/${projectId}/documents`, form, options);
}
export function normalizeDocuments(projectId, body, options) {
    return postJson(`${BASE}/projects/${projectId}/normalize`, body, options);
}
// --- Corpus snapshots ----------------------------------------------------- //
export function listCorpusSnapshots(projectId, params, options) {
    return getJson(`${BASE}/projects/${projectId}/corpus-snapshots${pageQuery(params)}`, options);
}
export async function listAllCorpusSnapshots(projectId, options) {
    return collectAllPages((params) => listCorpusSnapshots(projectId, params, options));
}
export function createCorpusSnapshot(body, options) {
    return postJson(`${BASE}/corpus-snapshots`, body, options);
}
// --- Releases (lectura + lifecycle) --------------------------------------- //
export function listReleases(projectId, params, options) {
    return getJson(`${BASE}/projects/${projectId}/releases${pageQuery(params)}`, options);
}
// El historial de releases es la evidencia del ciclo RAG por proyecto: se carga
// completo (todas las páginas) para que ninguna quede invisible al operador.
export async function listAllReleases(projectId, options) {
    return collectAllPages((params) => listReleases(projectId, params, options));
}
export function getRelease(releaseId, options) {
    return getJson(`${BASE}/releases/${releaseId}`, options);
}
export function createReleaseDraft(body, options) {
    return postJson(`${BASE}/releases`, body, options);
}
export function buildRelease(releaseId, options) {
    return postJson(`${BASE}/releases/${releaseId}/build`, {}, withIdempotency(options));
}
export function validateRelease(releaseId, options) {
    return postJson(`${BASE}/releases/${releaseId}/validate`, {}, withIdempotency(options));
}
export function publishRelease(releaseId, options) {
    return postJson(`${BASE}/releases/${releaseId}/publish`, {}, withIdempotency(options));
}
export function retireRelease(releaseId, body, options) {
    return postJson(`${BASE}/releases/${releaseId}/retire`, body, withIdempotency(options));
}
// --- Perfiles (read-model) ------------------------------------------------ //
export function listProcessingProfiles(projectId, options) {
    return getJson(`${BASE}/projects/${projectId}/processing-profiles`, options);
}
export function listChunkingProfiles(projectId, options) {
    return getJson(`${BASE}/projects/${projectId}/chunking-profiles`, options);
}
