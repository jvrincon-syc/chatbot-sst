// Etiquetas legibles de los enums de configuración de proyecto. Se comparten
// entre el alta (ProjectList) y la edición (ProjectConfigurationForm) para no
// duplicar el catálogo ni los labels. Los valores provienen del contrato
// (CorpusOrganizationPolicy / DocumentTypeTemplate); nada de negocio aquí.
import type {
  CorpusOrganizationPolicy,
  DocumentTypeTemplate,
} from "../platformTypes.js";

export const POLICY_OPTIONS: ReadonlyArray<{
  value: CorpusOrganizationPolicy;
  label: string;
}> = [
  { value: "source-folders-v1", label: "Carpetas de origen (v1)" },
  { value: "document-types-v1", label: "Tipos de documento (v1)" },
  { value: "hybrid-v1", label: "Híbrida (v1)" },
  { value: "sst-legacy-v1", label: "SST legacy (v1)" },
];

export const TEMPLATE_OPTIONS: ReadonlyArray<{
  value: DocumentTypeTemplate;
  label: string;
}> = [
  { value: "generic", label: "Genérica" },
  { value: "sst", label: "SST" },
];

const POLICY_VALUES = new Set<string>(POLICY_OPTIONS.map((option) => option.value));

// `ProjectConfigurationSchema` tipa la política y el template como `string` libre
// (lectura), así que al pasarlos al formulario editable se narrowa fail-safe al
// valor por defecto si el backend enviara algo fuera del enum conocido.
export function normalizePolicy(value: string): CorpusOrganizationPolicy {
  return POLICY_VALUES.has(value) ? (value as CorpusOrganizationPolicy) : "source-folders-v1";
}

export function normalizeTemplate(value: string): DocumentTypeTemplate {
  return value === "sst" ? "sst" : "generic";
}
