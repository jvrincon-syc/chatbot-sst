import { Copy, Loader2, Play } from "lucide-react";
import {
  chunkingProfileSummary,
  DEFAULT_CHUNKING_PROFILE_ID,
  type ChunkingFormState,
} from "../chunkingState.js";
import type { ChunkingProfile } from "../chunkingTypes.js";

export function ChunkingLaunchPanel({
  form,
  profiles,
  profilesError,
  profilesLoading,
  parsedDocumentIds,
  selectedProfile,
  busy,
  onChange,
  onLaunch,
  onRegenerateKey,
}: {
  form: ChunkingFormState;
  profiles: ChunkingProfile[];
  profilesError: string | null;
  profilesLoading: boolean;
  parsedDocumentIds: string[];
  selectedProfile: ChunkingProfile | null;
  busy: boolean;
  onChange: (value: Partial<ChunkingFormState>) => void;
  onLaunch: () => void;
  onRegenerateKey: () => void;
}) {
  const idCount = parsedDocumentIds.length;
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Lanzar corrida</h2>
          <span>Contratos locales, sin rutas arbitrarias ni embeddings.</span>
        </div>
        <span className="ui-pill">Idempotencia obligatoria</span>
      </div>
      <div className="ui-panel-body">
        <div className="ui-toggle-row" role="tablist" aria-label="Scope de chunking">
          <button
            type="button"
            className={form.scope === "documents" ? "ui-toggle active" : "ui-toggle"}
            onClick={() => onChange({ scope: "documents" })}
          >
            Documentos
          </button>
          <button
            type="button"
            className={form.scope === "corpus" ? "ui-toggle active" : "ui-toggle"}
            onClick={() => onChange({ scope: "corpus" })}
          >
            Corpus
          </button>
        </div>
        <label className="ui-field">
          Perfil
          <select
            value={form.profileId}
            disabled={profilesLoading || profiles.length === 0}
            onChange={(event) => onChange({ profileId: event.target.value })}
          >
            {profiles.length === 0 ? <option value={DEFAULT_CHUNKING_PROFILE_ID}>{DEFAULT_CHUNKING_PROFILE_ID}</option> : null}
            {profiles.map((profile) => (
              <option value={profile.profileId} key={profile.profileId}>
                {profile.profileId}
              </option>
            ))}
          </select>
          {profilesError ? <span className="ui-field-note error">{profilesError}</span> : null}
        </label>
        <label className="ui-field">
          Document IDs
          <textarea
            value={form.documentIdsInput}
            disabled={form.scope === "corpus"}
            placeholder="doc_001\ndoc_002"
            onChange={(event) => onChange({ documentIdsInput: event.target.value })}
          />
          <span className="ui-field-note">
            {form.scope === "corpus"
              ? "La corrida usara todos los documentos del inventario."
              : `${idCount} IDs detectados. Se aceptan lineas o comas.`}
          </span>
        </label>
        <div className="ui-inline-grid">
          <label className="ui-checkbox">
            <input
              type="checkbox"
              checked={form.force}
              onChange={(event) => onChange({ force: event.target.checked })}
            />
            Forzar reprocesado
          </label>
          <div className="ui-key-row">
            <label className="ui-field">
              Idempotency-Key
              <input
                value={form.idempotencyKey}
                onChange={(event) => onChange({ idempotencyKey: event.target.value })}
              />
            </label>
            <button className="secondary-button" type="button" onClick={onRegenerateKey}>
              <Copy size={16} />
              Regenerar
            </button>
          </div>
        </div>
        <div className="ui-actions">
          <button className="primary-button" type="button" onClick={onLaunch} disabled={busy}>
            {busy ? <Loader2 className="spin" size={16} /> : <Play size={16} />}
            Iniciar chunking
          </button>
          <span className="ui-hint">
            {selectedProfile ? chunkingProfileSummary(selectedProfile) : "Sin perfil cargado."}
          </span>
        </div>
      </div>
    </section>
  );
}
