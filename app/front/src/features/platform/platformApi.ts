// Cliente HTTP tipado de la superficie de plataforma (Fase 8, Task 4).
//
// Adaptador delgado sobre el cliente compartido `shared/api`: mismas garantías
// (envelope de error único, `credentials: "same-origin"`, cero bearer/localStorage;
// la auth va por la cookie de sesión de Gate 3). Los tipos vienen del OpenAPI
// generado (`platformTypes`), nunca de contratos a mano. No hay lógica de negocio
// aquí: valida y autoriza FastAPI.
import {
  buildQuery,
  createIdempotencyKey,
  getJson,
  patchJson,
  postJson,
  postMultipart,
  type PipelineGetOptions,
  type PipelinePostOptions,
} from "../../shared/api/apiClient.js";
import type {
  CorpusSnapshot,
  CreateCorpusSnapshotRequest,
  CreateProjectRequest,
  CreateReleaseDraftRequest,
  CreateVariantRequest,
  ChunkingProfileRead,
  NormalizeProjectDocumentsRequest,
  PaginatedCorpusSnapshots,
  PaginatedProjectDocuments,
  PaginatedProjects,
  PaginatedReleases,
  PaginatedVariants,
  ProcessingProfileRead,
  Project,
  ProjectConfiguration,
  ProjectDocumentRevision,
  ProjectNormalizeReport,
  Release,
  ReleaseBuildReport,
  RetireReleaseRequest,
  UpdateProjectConfigurationRequest,
  UpdateProjectRequest,
  Variant,
  VariantMatrixCell,
} from "./platformTypes.js";

const BASE = "/api/platform";

type PageParams = { page?: number; pageSize?: number };

function pageQuery(params?: PageParams): string {
  return buildQuery({ page: params?.page, page_size: params?.pageSize });
}

// Las mutaciones de release exigen `Idempotency-Key`. Se genera una por intento
// salvo que el caller reuse una para reintentar la MISMA operación (replay seguro).
function withIdempotency(options?: PipelinePostOptions): PipelinePostOptions {
  return { ...options, idempotencyKey: options?.idempotencyKey ?? createIdempotencyKey("platform") };
}

// --- Proyectos / configuración ------------------------------------------- //

export function listProjects(params?: PageParams, options?: PipelineGetOptions): Promise<PaginatedProjects> {
  return getJson<PaginatedProjects>(`${BASE}/projects${pageQuery(params)}`, options);
}

export function getProject(projectId: string, options?: PipelineGetOptions): Promise<Project> {
  return getJson<Project>(`${BASE}/projects/${projectId}`, options);
}

export function createProject(body: CreateProjectRequest, options?: PipelinePostOptions): Promise<Project> {
  return postJson<Project>(`${BASE}/projects`, body, options);
}

export function updateProject(
  projectId: string,
  body: UpdateProjectRequest,
  options?: PipelinePostOptions,
): Promise<Project> {
  return patchJson<Project>(`${BASE}/projects/${projectId}`, body, options);
}

export function getConfiguration(projectId: string, options?: PipelineGetOptions): Promise<ProjectConfiguration> {
  return getJson<ProjectConfiguration>(`${BASE}/projects/${projectId}/configuration`, options);
}

export function updateConfiguration(
  projectId: string,
  body: UpdateProjectConfigurationRequest,
  options?: PipelinePostOptions,
): Promise<ProjectConfiguration> {
  return patchJson<ProjectConfiguration>(`${BASE}/projects/${projectId}/configuration`, body, options);
}

// --- Variantes ------------------------------------------------------------ //

export function getVariantMatrix(projectId: string, options?: PipelineGetOptions): Promise<VariantMatrixCell[]> {
  return getJson<VariantMatrixCell[]>(`${BASE}/projects/${projectId}/variant-matrix`, options);
}

export function listVariants(
  projectId: string,
  params?: PageParams,
  options?: PipelineGetOptions,
): Promise<PaginatedVariants> {
  return getJson<PaginatedVariants>(`${BASE}/projects/${projectId}/variants${pageQuery(params)}`, options);
}

export function createVariant(
  projectId: string,
  body: CreateVariantRequest,
  options?: PipelinePostOptions,
): Promise<Variant> {
  return postJson<Variant>(`${BASE}/projects/${projectId}/variants`, body, options);
}

// --- Documentos (list / upload / normalize) ------------------------------- //

export function listDocuments(
  projectId: string,
  params?: PageParams,
  options?: PipelineGetOptions,
): Promise<PaginatedProjectDocuments> {
  return getJson<PaginatedProjectDocuments>(`${BASE}/projects/${projectId}/documents${pageQuery(params)}`, options);
}

// El read-model paginado devuelve 25 por defecto; el operador necesita el corpus
// completo (p. ej. 55 documentos). Recorre todas las páginas al máximo permitido
// (MAX_PAGE_SIZE=100) y devuelve el listado plano.
export async function listAllDocuments(
  projectId: string,
  options?: PipelineGetOptions,
): Promise<ProjectDocumentRevision[]> {
  const items: ProjectDocumentRevision[] = [];
  let page = 1;
  // Cota dura por si el backend reportara total_pages inconsistente (fail-safe).
  for (let guard = 0; guard < 1000; guard += 1) {
    const response = await listDocuments(projectId, { page, pageSize: 100 }, options);
    items.push(...response.items);
    if (page >= response.total_pages || response.items.length === 0) {
      break;
    }
    page += 1;
  }
  return items;
}

export function uploadDocument(
  projectId: string,
  file: File,
  sourceRelpath: string,
  options?: PipelinePostOptions,
): Promise<ProjectDocumentRevision> {
  const form = new FormData();
  form.append("file", file);
  form.append("source_relpath", sourceRelpath);
  return postMultipart<ProjectDocumentRevision>(`${BASE}/projects/${projectId}/documents`, form, options);
}

export function normalizeDocuments(
  projectId: string,
  body: NormalizeProjectDocumentsRequest,
  options?: PipelinePostOptions,
): Promise<ProjectNormalizeReport> {
  return postJson<ProjectNormalizeReport>(`${BASE}/projects/${projectId}/normalize`, body, options);
}

// --- Corpus snapshots ----------------------------------------------------- //

export function listCorpusSnapshots(
  projectId: string,
  params?: PageParams,
  options?: PipelineGetOptions,
): Promise<PaginatedCorpusSnapshots> {
  return getJson<PaginatedCorpusSnapshots>(
    `${BASE}/projects/${projectId}/corpus-snapshots${pageQuery(params)}`,
    options,
  );
}

export function createCorpusSnapshot(
  body: CreateCorpusSnapshotRequest,
  options?: PipelinePostOptions,
): Promise<CorpusSnapshot> {
  return postJson<CorpusSnapshot>(`${BASE}/corpus-snapshots`, body, options);
}

// --- Releases (lectura + lifecycle) --------------------------------------- //

export function listReleases(
  projectId: string,
  params?: PageParams,
  options?: PipelineGetOptions,
): Promise<PaginatedReleases> {
  return getJson<PaginatedReleases>(`${BASE}/projects/${projectId}/releases${pageQuery(params)}`, options);
}

export function getRelease(releaseId: string, options?: PipelineGetOptions): Promise<Release> {
  return getJson<Release>(`${BASE}/releases/${releaseId}`, options);
}

export function createReleaseDraft(
  body: CreateReleaseDraftRequest,
  options?: PipelinePostOptions,
): Promise<Release> {
  return postJson<Release>(`${BASE}/releases`, body, options);
}

export function buildRelease(releaseId: string, options?: PipelinePostOptions): Promise<ReleaseBuildReport> {
  return postJson<ReleaseBuildReport>(`${BASE}/releases/${releaseId}/build`, {}, withIdempotency(options));
}

export function validateRelease(releaseId: string, options?: PipelinePostOptions): Promise<Release> {
  return postJson<Release>(`${BASE}/releases/${releaseId}/validate`, {}, withIdempotency(options));
}

export function publishRelease(releaseId: string, options?: PipelinePostOptions): Promise<Release> {
  return postJson<Release>(`${BASE}/releases/${releaseId}/publish`, {}, withIdempotency(options));
}

export function retireRelease(
  releaseId: string,
  body: RetireReleaseRequest,
  options?: PipelinePostOptions,
): Promise<Release> {
  return postJson<Release>(`${BASE}/releases/${releaseId}/retire`, body, withIdempotency(options));
}

// --- Perfiles (read-model) ------------------------------------------------ //

export function listProcessingProfiles(
  projectId: string,
  options?: PipelineGetOptions,
): Promise<ProcessingProfileRead[]> {
  return getJson<ProcessingProfileRead[]>(`${BASE}/projects/${projectId}/processing-profiles`, options);
}

export function listChunkingProfiles(
  projectId: string,
  options?: PipelineGetOptions,
): Promise<ChunkingProfileRead[]> {
  return getJson<ChunkingProfileRead[]>(`${BASE}/projects/${projectId}/chunking-profiles`, options);
}
