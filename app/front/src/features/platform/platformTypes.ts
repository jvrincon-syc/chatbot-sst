// Aliases de los schemas de plataforma derivados del OpenAPI generado. NO se
// escribe ningún contrato a mano: si el backend cambia, se regenera
// `platformOpenApi.generated.ts` (`npm run api:generate`) y estos alias siguen.
import type { components } from "./platformOpenApi.generated.js";

type Schemas = components["schemas"];

// Proyectos / configuración
export type Project = Schemas["ProjectSchema"];
export type PaginatedProjects = Schemas["PaginatedProjectsSchema"];
export type ProjectConfiguration = Schemas["ProjectConfigurationSchema"];
export type CreateProjectRequest = Schemas["CreateProjectRequestSchema"];
export type UpdateProjectRequest = Schemas["UpdateProjectRequestSchema"];
export type UpdateProjectConfigurationRequest = Schemas["UpdateProjectConfigurationRequestSchema"];

// Variantes
export type Variant = Schemas["VariantSchema"];
export type PaginatedVariants = Schemas["PaginatedVariantsSchema"];
export type VariantMatrixCell = Schemas["VariantMatrixCellSchema"];
export type CreateVariantRequest = Schemas["CreateVariantRequestSchema"];

// Documentos (intake project-aware)
export type ProjectDocumentRevision = Schemas["ProjectDocumentRevisionSchema"];
export type PaginatedProjectDocuments = Schemas["PaginatedProjectDocumentsSchema"];
export type NormalizeProjectDocumentsRequest = Schemas["NormalizeProjectDocumentsRequestSchema"];
export type ProjectNormalizeReport = Schemas["ProjectNormalizeReportSchema"];

// Corpus snapshots
export type CorpusSnapshot = Schemas["CorpusSnapshotSchema"];
export type PaginatedCorpusSnapshots = Schemas["PaginatedCorpusSnapshotsSchema"];
export type CreateCorpusSnapshotRequest = Schemas["CreateCorpusSnapshotRequestSchema"];

// Releases
export type Release = Schemas["ReleaseSchema"];
export type PaginatedReleases = Schemas["PaginatedReleasesSchema"];
export type CreateReleaseDraftRequest = Schemas["CreateReleaseDraftRequestSchema"];
export type RetireReleaseRequest = Schemas["RetireReleaseRequestSchema"];
export type ReleaseBuildReport = Schemas["ReleaseBuildReportSchema"];

// Perfiles (read-model)
export type ProcessingProfileRead = Schemas["ProcessingProfileReadSchema"];
export type ChunkingProfileRead = Schemas["ChunkingProfileReadSchema"];
