import { AlertCircle, Ban, CheckCircle2, Loader2 } from "lucide-react";
import {
  embeddingCatalogFullyBlocked,
  embeddingProfileBlockedReason,
  embeddingProfileSelectable,
} from "../embeddingState.js";
import type { EmbeddingProfile } from "../embeddingTypes.js";

type EmbeddingCatalogPanelProps = {
  profiles: EmbeddingProfile[];
  loading: boolean;
  error: string | null;
  selectedProfileId: string | null;
  onSelectProfile: (profileId: string) => void;
};

const SELECT_LABEL_ID = "embedding-profile-select-label";
const HELP_ID = "embedding-profile-help";

// Presents the read-only embedding profile catalog. Every profile is shown, and
// blocked profiles keep their machine reason visible in text (not only color).
// The catalog must render cleanly even when every profile is blocked today.
export function EmbeddingCatalogPanel({
  profiles,
  loading,
  error,
  selectedProfileId,
  onSelectProfile,
}: EmbeddingCatalogPanelProps) {
  const fullyBlocked = embeddingCatalogFullyBlocked(profiles);
  const hasProfiles = profiles.length > 0;
  const blockedReasonsSummary = Array.from(
    new Set(
      profiles
        .filter((profile) => !embeddingProfileSelectable(profile))
        .map((profile) => embeddingProfileBlockedReason(profile))
        .filter((reason): reason is string => reason !== null),
    ),
  ).join(", ");

  return (
    <section className="panel chunking-panel" aria-label="Catalogo de perfiles de embedding">
      <div className="panel-heading">
        <div>
          <h2>Perfiles de embedding</h2>
          <span>Metadata de solo lectura. Solo se puede elegir un perfil habilitado para documentos.</span>
        </div>
        <span className="chunking-pill">Bundle-first</span>
      </div>

      <div className="chunking-panel-body">
        {error ? (
          <div className="notice notice-danger" role="alert">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        ) : null}

        {loading ? (
          <div className="chunking-launch-hint" role="status">
            <Loader2 className="spin" size={16} /> Cargando perfiles...
          </div>
        ) : null}

        {!loading && !error && !hasProfiles ? (
          <div className="chunking-empty" role="status">
            <span>No hay perfiles de embedding disponibles.</span>
          </div>
        ) : null}

        {!loading && hasProfiles ? (
          <label className="chunking-field">
            <span id={SELECT_LABEL_ID}>Perfil de embedding</span>
            <select
              aria-labelledby={SELECT_LABEL_ID}
              aria-describedby={HELP_ID}
              value={selectedProfileId ?? ""}
              onChange={(event) => onSelectProfile(event.currentTarget.value)}
            >
              <option value="" disabled>
                Selecciona un perfil habilitado
              </option>
              {profiles.map((profile) => {
                const selectable = embeddingProfileSelectable(profile);
                const reason = embeddingProfileBlockedReason(profile);
                return (
                  <option key={profile.profileId} value={profile.profileId} disabled={!selectable}>
                    {profile.profileId}
                    {selectable ? "" : ` — bloqueado (${reason ?? "no disponible"})`}
                  </option>
                );
              })}
            </select>
            <span className="chunking-field-note" id={HELP_ID}>
              Los perfiles bloqueados no pueden ejecutar embedding de documentos hasta la verificacion del backend.
            </span>
          </label>
        ) : null}

        {fullyBlocked ? (
          <div className="chunking-warning-box" role="status" aria-label="Catalogo de embedding bloqueado">
            <div className="chunking-status-row">
              <Ban size={16} aria-hidden="true" />
              <strong>Ningun perfil habilitado para embedding de documentos</strong>
            </div>
            <span>
              Hoy ningun perfil puede ejecutar embedding de documentos.
              {blockedReasonsSummary
                ? ` Motivo: ${blockedReasonsSummary}.`
                : ""}{" "}
              Es la respuesta fail-closed correcta del backend; no se habilita ni se simula un flujo
              exitoso hasta la verificacion del backend.
            </span>
          </div>
        ) : null}

        {!loading && hasProfiles ? (
          <ul className="chunking-list" aria-label="Estado de cada perfil">
            {profiles.map((profile) => {
              const selectable = embeddingProfileSelectable(profile);
              const reason = embeddingProfileBlockedReason(profile);
              return (
                <li key={profile.profileId} className="chunking-profile-state">
                  <span>{profile.profileId}</span>
                  <strong>
                    {profile.provider} · {profile.model} · dim {profile.dimension}
                  </strong>
                  <span
                    className={
                      selectable ? "chunking-status-chip success" : "chunking-status-chip danger"
                    }
                  >
                    {selectable ? (
                      <>
                        <CheckCircle2 size={13} aria-hidden="true" /> Habilitado
                      </>
                    ) : (
                      <>
                        <Ban size={13} aria-hidden="true" /> Bloqueado: {reason ?? "no disponible"}
                      </>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
