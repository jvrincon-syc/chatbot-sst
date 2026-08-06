import type { AppView } from "./dashboardTypes.js";
import { viewTitles } from "./dashboardTypes.js";

export type DashboardViewDefinition = {
  view: AppView;
  sidebarLabel: string;
  switcherLabel: string;
  title: string;
};

export const DASHBOARD_VIEWS: readonly DashboardViewDefinition[] = [
  {
    view: "operations",
    sidebarLabel: "Operacion",
    switcherLabel: "Operacion",
    title: viewTitles.operations,
  },
  {
    view: "review",
    sidebarLabel: "Revision",
    switcherLabel: "Revision",
    title: viewTitles.review,
  },
  {
    view: "inventory",
    sidebarLabel: "Inventario",
    switcherLabel: "Inventario",
    title: viewTitles.inventory,
  },
  {
    view: "chunking",
    sidebarLabel: "Chunking",
    switcherLabel: "Chunking",
    title: viewTitles.chunking,
  },
  {
    view: "embedding-indexing",
    sidebarLabel: "Embedding/Indexing",
    switcherLabel: "Emb/Idx",
    title: viewTitles["embedding-indexing"],
  },
];

const DASHBOARD_VIEW_SET = new Set<AppView>(DASHBOARD_VIEWS.map((item) => item.view));

export function isDashboardView(value: unknown): value is AppView {
  return typeof value === "string" && DASHBOARD_VIEW_SET.has(value as AppView);
}
