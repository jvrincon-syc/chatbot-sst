import { Hammer } from "lucide-react";
import type { BuildReportState } from "./useRagReleaseWorkspace.js";

// Informe del último build de la release seleccionada. Tres métricas del contrato
// ReleaseBuildReport: revisiones construidas, etapas reutilizadas y etapas nuevas.
export function BuildReport({ state }: { state: BuildReportState }) {
  if (state.status === "idle") {
    return (
      <div className="ui-empty">
        <Hammer size={22} />
        <span>Ejecuta un build sobre una release en draft para ver el informe.</span>
      </div>
    );
  }

  const { report } = state;
  return (
    <dl className="build-report" aria-label="Informe de build">
      <div className="build-report-tile">
        <dt>Revisiones construidas</dt>
        <dd>{report.revisions_built}</dd>
      </div>
      <div className="build-report-tile">
        <dt>Etapas construidas</dt>
        <dd>{report.built_stages}</dd>
      </div>
      <div className="build-report-tile">
        <dt>Etapas reutilizadas</dt>
        <dd>{report.reused_stages}</dd>
      </div>
    </dl>
  );
}
