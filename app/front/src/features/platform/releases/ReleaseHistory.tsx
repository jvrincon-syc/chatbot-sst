import { History } from "lucide-react";
import type { Release } from "../platformTypes.js";

// Historial de releases del proyecto (read-model rehidratable). Marca la seleccionada
// (persistida como ID de navegación) con `aria-current` para que sobreviva a un
// refresh. `release_manifest_hash` es la firma inmutable de procedencia.
export function ReleaseHistory({
  releases,
  selectedReleaseId,
  onSelect,
}: {
  releases: Release[];
  selectedReleaseId: string | null;
  onSelect: (releaseId: string) => void;
}) {
  if (releases.length === 0) {
    return (
      <div className="ui-empty">
        <History size={22} />
        <span>Este proyecto aún no tiene releases. Crea el primer draft desde el formulario.</span>
      </div>
    );
  }

  return (
    <ul className="ui-list" aria-label="Historial de releases">
      {releases.map((release) => {
        const active = release.rag_release_id === selectedReleaseId;
        return (
          <li key={release.rag_release_id}>
            <button
              type="button"
              className={active ? "ui-list-item active" : "ui-list-item"}
              aria-current={active ? "true" : undefined}
              onClick={() => onSelect(release.rag_release_id)}
            >
              <strong>
                <code>{release.rag_release_id}</code>
              </strong>
              <span>
                release #{release.release_number} ·{" "}
                <span className="ui-status-chip neutral">{release.state}</span>
              </span>
              <span>
                manifest{" "}
                <code title="Firma inmutable de procedencia">
                  {release.release_manifest_hash ?? "—"}
                </code>
              </span>
              <small>{release.created_at}</small>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
