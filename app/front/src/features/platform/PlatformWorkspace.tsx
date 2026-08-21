import { useState } from "react";
import { ProjectWorkspace } from "./projects/ProjectWorkspace.js";
import { VariantMatrixWorkspace } from "./variants/VariantMatrixWorkspace.js";
import { DocumentIntakeWorkspace } from "./documents/DocumentIntakeWorkspace.js";
import { CorpusSnapshotWorkspace } from "./corpus/CorpusSnapshotWorkspace.js";
import { RagReleaseWorkspace } from "./releases/RagReleaseWorkspace.js";
import { PLATFORM_VIEWS, type PlatformView } from "./platformNavigation.js";

// Contenedor de la superficie Platform: posee la sub-nav (estado de sesion, no
// persistido) y monta el workspace activo. Reusa `.view-switcher` del shell.
export function PlatformWorkspace() {
  const [view, setView] = useState<PlatformView>("projects");

  return (
    <div className="platform-surface">
      <nav className="view-switcher platform-views" aria-label="Vista de plataforma">
        {PLATFORM_VIEWS.map((item) => (
          <button
            key={item.view}
            type="button"
            className={view === item.view ? "active" : ""}
            aria-current={view === item.view ? "page" : undefined}
            onClick={() => setView(item.view)}
            title={item.title}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <PlatformView view={view} />
    </div>
  );
}

function PlatformView({ view }: { view: PlatformView }) {
  switch (view) {
    case "projects":
      return <ProjectWorkspace />;
    case "variants":
      return <VariantMatrixWorkspace />;
    case "documents":
      return <DocumentIntakeWorkspace />;
    case "corpus":
      return <CorpusSnapshotWorkspace />;
    case "releases":
      return <RagReleaseWorkspace />;
  }
}
