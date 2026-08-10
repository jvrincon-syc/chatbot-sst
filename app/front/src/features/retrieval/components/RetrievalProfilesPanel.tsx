import { ArrowRight, CheckCircle2, Loader2, Search, ShieldAlert } from "lucide-react";
import {
  retrievalRuntimeStatusLabel,
  retrievalRuntimeStatusTone,
  retrievalValidationStatusLabel,
  retrievalValidationStatusTone,
} from "../retrievalState.js";
import type { RetrievalProfile } from "../retrievalTypes.js";

type RetrievalProfilesPanelProps = {
  profiles: RetrievalProfile[];
  loading: boolean;
  error: string | null;
  selectedProfileId: string | null;
  onSelectProfile: (profileId: string) => void;
};

// The retrieval stage gets its own catalog surface so the UI is not limited to
// the single profile handed back by activation. It remains read-only here: the
// operator can select and inspect a profile, while activation still lives in the
// indexing stage.
export function RetrievalProfilesPanel({
  profiles,
  loading,
  error,
  selectedProfileId,
  onSelectProfile,
}: RetrievalProfilesPanelProps) {
  return (
    <section className="panel" aria-label="Catalogo de retrieval">
      <div className="panel-heading">
        <div>
          <h2>Perfiles de retrieval</h2>
          <span>Catalogo de solo lectura con estado activo, validacion y runtime.</span>
        </div>
        <span className="ui-pill">
          <Search size={13} aria-hidden="true" /> API /profiles
        </span>
      </div>

      <div className="ui-panel-body">
        {error ? (
          <div className="notice notice-danger" role="alert">
            <ShieldAlert size={16} />
            <span>{error}</span>
          </div>
        ) : null}

        {loading ? (
          <div className="ui-hint" role="status">
            <Loader2 className="spin" size={16} /> Cargando perfiles de retrieval...
          </div>
        ) : null}

        {!loading && !error && profiles.length === 0 ? (
          <div className="ui-empty" role="status">
            <span>No hay perfiles de retrieval registrados.</span>
          </div>
        ) : null}

        {profiles.length > 0 ? (
          <ul className="ui-list" aria-label="Listado de perfiles de retrieval">
            {profiles.map((profile) => {
              const selected = profile.retrievalProfileId === selectedProfileId;
              return (
                <li key={profile.retrievalProfileId}>
                  <button
                    type="button"
                    className={selected ? "ui-list-item active" : "ui-list-item"}
                    aria-pressed={selected}
                    onClick={() => onSelectProfile(profile.retrievalProfileId)}
                  >
                    <span>{profile.retrievalProfileId}</span>
                    <strong>
                      {profile.consumerScopeType}/{profile.consumerScopeId} ·{" "}
                      {profile.embeddingProfileId}
                    </strong>
                    <small>
                      Validacion {retrievalValidationStatusLabel(profile.validationStatus)} ·{" "}
                      Runtime {retrievalRuntimeStatusLabel(profile.lastRuntimeStatus)}
                    </small>
                    <div className="ui-status-row">
                      <span
                        className={`ui-status-chip ${retrievalValidationStatusTone(
                          profile.validationStatus,
                        )}`}
                      >
                        {profile.active ? (
                          <>
                            <CheckCircle2 size={13} aria-hidden="true" /> Activo
                          </>
                        ) : (
                          <>
                            <ArrowRight size={13} aria-hidden="true" /> Inactivo
                          </>
                        )}
                      </span>
                      <span
                        className={`ui-status-chip ${retrievalRuntimeStatusTone(
                          profile.lastRuntimeStatus,
                        )}`}
                      >
                        Runtime
                      </span>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
