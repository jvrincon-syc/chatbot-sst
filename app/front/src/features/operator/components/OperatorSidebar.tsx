import { History, Layers, LayoutGrid } from "lucide-react";
import {
  OPERATOR_SURFACES,
  type OperatorSurface,
} from "../operatorNavigation.js";

const SURFACE_ICONS: Record<OperatorSurface, typeof LayoutGrid> = {
  platform: LayoutGrid,
  legacy: History,
};

export function OperatorSidebar({
  activeSurface,
  onSurfaceChange,
}: {
  activeSurface: OperatorSurface;
  onSurfaceChange: (surface: OperatorSurface) => void;
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
    </aside>
  );
}
