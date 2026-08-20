import { useState } from "react";
import { FolderPlus } from "lucide-react";
import { DashboardApp } from "../dashboard/DashboardApp.js";
import { OperatorSidebar } from "./components/OperatorSidebar.js";
import type { OperatorSurface } from "./operatorNavigation.js";

// La superficie activa es estado de sesion: no se persiste. Task 7 reemplaza el
// placeholder de "platform" por el ProjectWorkspace real.
export function OperatorApp() {
  const [surface, setSurface] = useState<OperatorSurface>("platform");

  return (
    <div className="operator-shell">
      <OperatorSidebar activeSurface={surface} onSurfaceChange={setSurface} />
      {surface === "legacy" ? <DashboardApp /> : <PlatformPlaceholder />}
    </div>
  );
}

function PlatformPlaceholder() {
  return (
    <main className="workspace operator-workspace">
      <header className="topbar">
        <div>
          <h1>RAG Platform</h1>
          <p>Administracion de proyectos, normalizacion, variantes y releases.</p>
        </div>
      </header>

      <section className="operator-empty" aria-label="Estado inicial de RAG Platform">
        <span className="operator-empty-icon" aria-hidden="true">
          <FolderPlus size={28} />
        </span>
        <h2>Selecciona o crea un proyecto para empezar</h2>
        <p>
          Aqui se administra el ciclo completo: proyecto, normalizacion, variante,
          snapshot y release.
        </p>
      </section>
    </main>
  );
}
