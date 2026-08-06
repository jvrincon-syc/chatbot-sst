import {
  Boxes,
  Clock3,
  Database,
  FileText,
  SplitSquareHorizontal,
  UploadCloud,
} from "lucide-react";
import { DASHBOARD_VIEWS } from "../dashboardNavigation.js";
import type { AppView } from "../dashboardTypes.js";

const SIDEBAR_ICONS: Record<AppView, typeof UploadCloud> = {
  operations: UploadCloud,
  review: Clock3,
  inventory: Database,
  chunking: SplitSquareHorizontal,
  "embedding-indexing": Boxes,
};

export function DashboardSidebar({
  activeView,
  onViewChange,
}: {
  activeView: AppView;
  onViewChange: (view: AppView) => void;
}) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <FileText size={24} />
        <span>SST Pipeline</span>
      </div>
      <nav>
        {DASHBOARD_VIEWS.map((item) => {
          const Icon = SIDEBAR_ICONS[item.view];
          return (
            <button
              className={activeView === item.view ? "nav-item active" : "nav-item"}
              key={item.view}
              onClick={() => onViewChange(item.view)}
              type="button"
            >
              <Icon size={18} />
              {item.sidebarLabel}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
