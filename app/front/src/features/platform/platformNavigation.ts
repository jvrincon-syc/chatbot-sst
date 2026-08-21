// Vistas dentro de la superficie Platform. Tipo separado de `OperatorSurface`
// (platform | legacy) y de `AppView` (dashboard legacy): una vista de plataforma
// no es una pantalla del dashboard. El array es la fuente única para la sub-nav;
// las Tasks 9-13 añaden documents/snapshots/releases aquí sin tocar el shell.
export type PlatformView = "projects" | "documents" | "variants" | "corpus" | "releases";

export type PlatformViewDefinition = {
  view: PlatformView;
  label: string;
  title: string;
};

// Orden = secuencia real del operador: alta/config → intake+normalize → receta
// → snapshot. Releases se añade en Task 11.
export const PLATFORM_VIEWS: readonly PlatformViewDefinition[] = [
  { view: "projects", label: "Projects", title: "Proyectos y configuración" },
  { view: "documents", label: "Documents", title: "Intake RAW y normalización" },
  { view: "variants", label: "Variants", title: "Matriz de variantes y recetas" },
  { view: "corpus", label: "Corpus", title: "Snapshots de corpus" },
  { view: "releases", label: "Releases", title: "Lifecycle de releases RAG" },
];

const PLATFORM_VIEW_SET = new Set<PlatformView>(PLATFORM_VIEWS.map((item) => item.view));

export function isPlatformView(value: unknown): value is PlatformView {
  return typeof value === "string" && PLATFORM_VIEW_SET.has(value as PlatformView);
}
