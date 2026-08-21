import { History, Layers, LayoutGrid, Loader2, LogOut } from "lucide-react";
import {
  OPERATOR_SURFACES,
  type OperatorSurface,
} from "../operatorNavigation.js";
import type { AuthenticatedOperatorSession } from "../operatorAuthApi.js";

const SURFACE_ICONS: Record<OperatorSurface, typeof LayoutGrid> = {
  platform: LayoutGrid,
  legacy: History,
};

export function OperatorSidebar({
  activeSurface,
  onSurfaceChange,
  session,
  loggingOut,
  onLogout,
}: {
  activeSurface: OperatorSurface;
  onSurfaceChange: (surface: OperatorSurface) => void;
  session: AuthenticatedOperatorSession;
  loggingOut: boolean;
  onLogout: () => void;
}) {
  return (
    <aside className="operator-rail">
      <div className="brand">
        <Layers size={24} />
        <span>RAG Platform</span>
      </div>
      <nav aria-label="Superficies de operador">
        {OPERATOR_SURFACES.map((item) => {
          const Icon = SURFACE_ICONS[item.surface];
          const active = activeSurface === item.surface;
          return (
            <button
              aria-current={active ? "page" : undefined}
              className={active ? "nav-item active" : "nav-item"}
              key={item.surface}
              onClick={() => onSurfaceChange(item.surface)}
              type="button"
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="operator-rail-footer">
        <div className="operator-session-card">
          <span>Sesión</span>
          <strong>{session.principal_id}</strong>
          <small>{scopeLabel(session.project_scope)}</small>
        </div>
        <button className="ghost-button operator-logout" type="button" onClick={onLogout}>
          {loggingOut ? <Loader2 className="spin" size={14} /> : <LogOut size={14} />}
          Cerrar sesión
        </button>
      </div>
    </aside>
  );
}

function scopeLabel(projectScope: string[] | null): string {
  // null = operador global (sin recorte); una lista = scope real del bearer.
  if (projectScope === null || projectScope.length === 0) {
    return "Todos los proyectos";
  }
  if (projectScope.length === 1) {
    return projectScope[0];
  }
  return `${projectScope.length} proyectos`;
}
