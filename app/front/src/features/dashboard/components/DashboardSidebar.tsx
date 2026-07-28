import { Clock3, Database, FileText, SplitSquareHorizontal, UploadCloud } from "lucide-react";
import type { AppView } from "../dashboardTypes.js";

export function DashboardSidebar({
  activeView,
  onViewChange,
}: {
  activeView: AppView;
  onViewChange: (view: AppView) => void;
}) {
  const items = [
    { label: "Operacion", icon: UploadCloud, view: "operations" as const },
    { label: "Revision", icon: Clock3, view: "review" as const },
    { label: "Inventario", icon: Database, view: "inventory" as const },
    { label: "Chunking", icon: SplitSquareHorizontal, view: "chunking" as const },
  ];

  return (
    <aside className="sidebar">
      <div className="brand">
        <FileText size={24} />
        <span>SST Pipeline</span>
      </div>
      <nav>
        {items.map((item) => (
          <button
            className={activeView === item.view ? "nav-item active" : "nav-item"}
            key={item.label}
            onClick={() => onViewChange(item.view)}
            type="button"
          >
            <item.icon size={18} />
            {item.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}
