import { AlertCircle, Blocks, Loader2, RefreshCw } from "lucide-react";
import { chunkingProfileSummary } from "../chunkingState.js";
import type { ChunkingProfile, ChunkingRunSummary } from "../chunkingTypes.js";

export function ChunkingProfilePanel({
  profile,
  profilesLoading,
  status,
  runLoading,
  onRefresh,
}: {
  profile: ChunkingProfile | null;
  profilesLoading: boolean;
  status: ChunkingRunSummary | null;
  runLoading: boolean;
  onRefresh: () => void;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Perfil activo</h2>
          <span>Resumen de la configuracion local y del ultimo estado cargado.</span>
        </div>
        <button className="ghost-button" type="button" onClick={onRefresh} disabled={runLoading}>
          <RefreshCw size={16} />
          Actualizar
        </button>
      </div>
      {profilesLoading ? (
        <div className="ui-empty">
          <Loader2 className="spin" size={20} />
          <span>Cargando perfiles locales...</span>
        </div>
      ) : profile ? (
        <div className="ui-panel-body">
          <dl className="ui-data-grid">
            <div>
              <dt>Perfil</dt>
              <dd>{profile.profileId}</dd>
            </div>
            <div>
              <dt>Children min</dt>
              <dd>{profile.childMinTokens}</dd>
            </div>
            <div>
              <dt>Target</dt>
              <dd>{profile.childTargetTokens}</dd>
            </div>
            <div>
              <dt>Max</dt>
              <dd>{profile.childMaxTokens}</dd>
            </div>
            <div>
              <dt>Overlap</dt>
              <dd>{Math.round(profile.overlapRatio * 100)}%</dd>
            </div>
            <div>
              <dt>Overlap min/max</dt>
              <dd>
                {profile.overlapMinTokens} / {profile.overlapMaxTokens}
              </dd>
            </div>
          </dl>
          <div className="ui-note">
            <Blocks size={16} />
            <span>{chunkingProfileSummary(profile)}</span>
          </div>
          <div className="ui-state-card">
            <span>Ultima corrida</span>
            <strong>{status ? `${status.status} · ${status.runId.slice(0, 12)}...` : "Sin corrida"}</strong>
          </div>
        </div>
      ) : (
        <div className="ui-empty">
          <AlertCircle size={20} />
          <span>No hay perfiles disponibles para chunking.</span>
        </div>
      )}
    </section>
  );
}
