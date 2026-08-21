import { useState, type FormEvent } from "react";
import { Check, Loader2, Lock, Plus, Save, Trash2 } from "lucide-react";
import type {
  CorpusOrganizationPolicy,
  DocumentTypeTemplate,
  Project,
  ProjectConfiguration,
  ProjectDocumentType,
  ProjectEmbeddingProfile,
  UpdateProjectConfigurationRequest,
} from "../platformTypes.js";
import {
  POLICY_OPTIONS,
  TEMPLATE_OPTIONS,
  normalizePolicy,
  normalizeTemplate,
} from "./projectOptions.js";

// Presentación pura del detalle del proyecto seleccionado. El componente se
// remonta (key = project_id + version en el contenedor) para reinicializar los
// drafts desde la configuración recién cargada/guardada. NUNCA pide ni muestra un
// indexing_target físico: los target_bindings son solo lectura.
export function ProjectConfigurationForm({
  project,
  configuration,
  renaming,
  saving,
  onRename,
  onSaveConfiguration,
}: {
  project: Project;
  configuration: ProjectConfiguration;
  renaming: boolean;
  saving: boolean;
  onRename: (displayName: string) => Promise<boolean>;
  onSaveConfiguration: (body: UpdateProjectConfigurationRequest) => Promise<boolean>;
}) {
  const [displayName, setDisplayName] = useState(project.display_name);
  const [policy, setPolicy] = useState<CorpusOrganizationPolicy>(
    normalizePolicy(configuration.corpus_organization_policy),
  );
  const [documentTypes, setDocumentTypes] = useState<ProjectDocumentType[]>(() =>
    configuration.document_types.map((type) => ({
      code: type.code,
      display_name: type.display_name,
      template: normalizeTemplate(type.template),
    })),
  );
  const [embeddingProfiles, setEmbeddingProfiles] = useState<ProjectEmbeddingProfile[]>(() =>
    configuration.embedding_profiles.map((profile) => ({
      embedding_profile_id: profile.embedding_profile_id,
      enabled: profile.enabled,
    })),
  );

  const nameChanged = displayName.trim().length > 0 && displayName.trim() !== project.display_name;

  function updateDocumentType(index: number, patch: Partial<ProjectDocumentType>) {
    setDocumentTypes((current) =>
      current.map((type, position) => (position === index ? { ...type, ...patch } : type)),
    );
  }

  function updateEmbeddingProfile(index: number, patch: Partial<ProjectEmbeddingProfile>) {
    setEmbeddingProfiles((current) =>
      current.map((profile, position) =>
        position === index ? { ...profile, ...patch } : profile,
      ),
    );
  }

  function handleRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!nameChanged || renaming) {
      return;
    }
    void onRename(displayName.trim());
  }

  function handleSaveConfiguration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) {
      return;
    }
    void onSaveConfiguration({
      corpus_organization_policy: policy,
      document_types: documentTypes.map((type) => ({
        code: type.code.trim(),
        display_name: type.display_name.trim(),
        template: type.template,
      })),
      embedding_profiles: embeddingProfiles.map((profile) => ({
        embedding_profile_id: profile.embedding_profile_id.trim(),
        enabled: profile.enabled,
      })),
    });
  }

  return (
    <section className="panel" aria-label="Configuración del proyecto">
      <div className="panel-heading">
        <div>
          <h2>{project.display_name}</h2>
          <span>{project.project_id}</span>
        </div>
        <span className="ui-pill" aria-label={`Versión de configuración ${configuration.version}`}>
          Config v{configuration.version}
        </span>
      </div>

      <div className="ui-panel-body">
        <form className="platform-rename" onSubmit={handleRename}>
          <div className="ui-field">
            <label htmlFor="project-display-name">Nombre visible</label>
            <div className="ui-key-row">
              <input
                id="project-display-name"
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
              />
              <button className="secondary-button" type="submit" disabled={!nameChanged || renaming}>
                {renaming ? <Loader2 className="spin" size={16} /> : <Check size={16} />}
                Guardar nombre
              </button>
            </div>
            <span className="ui-field-note">
              El slug es inmutable; solo cambia el nombre visible.
            </span>
          </div>
        </form>

        <form className="platform-config" onSubmit={handleSaveConfiguration}>
          <div className="ui-field">
            <label htmlFor="config-policy">Política de organización del corpus</label>
            <select
              id="config-policy"
              value={policy}
              onChange={(event) => setPolicy(event.target.value as CorpusOrganizationPolicy)}
            >
              {POLICY_OPTIONS.map((option) => (
                <option value={option.value} key={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <fieldset className="platform-fieldset">
            <legend>Tipos de documento</legend>
            <div className="ui-list compact">
              {documentTypes.length === 0 ? (
                <p className="ui-field-note">Sin tipos declarados en esta versión.</p>
              ) : (
                documentTypes.map((type, index) => (
                  <div className="platform-row" key={index}>
                    <div className="ui-field">
                      <label htmlFor={`doctype-code-${index}`}>Código</label>
                      <input
                        id={`doctype-code-${index}`}
                        value={type.code}
                        onChange={(event) => updateDocumentType(index, { code: event.target.value })}
                      />
                    </div>
                    <div className="ui-field">
                      <label htmlFor={`doctype-name-${index}`}>Nombre visible</label>
                      <input
                        id={`doctype-name-${index}`}
                        value={type.display_name}
                        onChange={(event) =>
                          updateDocumentType(index, { display_name: event.target.value })
                        }
                      />
                    </div>
                    <div className="ui-field">
                      <label htmlFor={`doctype-template-${index}`}>Plantilla</label>
                      <select
                        id={`doctype-template-${index}`}
                        value={type.template}
                        onChange={(event) =>
                          updateDocumentType(index, {
                            template: event.target.value as DocumentTypeTemplate,
                          })
                        }
                      >
                        {TEMPLATE_OPTIONS.map((option) => (
                          <option value={option.value} key={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={() =>
                        setDocumentTypes((current) =>
                          current.filter((_, position) => position !== index),
                        )
                      }
                      aria-label={`Quitar tipo de documento ${type.code || index + 1}`}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))
              )}
            </div>
            <div className="ui-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() =>
                  setDocumentTypes((current) => [
                    ...current,
                    { code: "", display_name: "", template: "generic" },
                  ])
                }
              >
                <Plus size={16} />
                Agregar tipo
              </button>
            </div>
          </fieldset>

          <fieldset className="platform-fieldset">
            <legend>Perfiles de embedding</legend>
            <div className="ui-list compact">
              {embeddingProfiles.length === 0 ? (
                <p className="ui-field-note">Sin perfiles habilitados en esta versión.</p>
              ) : (
                embeddingProfiles.map((profile, index) => (
                  <div className="platform-row embedding" key={index}>
                    <div className="ui-field">
                      <label htmlFor={`embedding-id-${index}`}>Embedding profile id</label>
                      <input
                        id={`embedding-id-${index}`}
                        value={profile.embedding_profile_id}
                        onChange={(event) =>
                          updateEmbeddingProfile(index, {
                            embedding_profile_id: event.target.value,
                          })
                        }
                      />
                    </div>
                    <label className="ui-checkbox" htmlFor={`embedding-enabled-${index}`}>
                      <input
                        id={`embedding-enabled-${index}`}
                        type="checkbox"
                        checked={profile.enabled}
                        onChange={(event) =>
                          updateEmbeddingProfile(index, { enabled: event.target.checked })
                        }
                      />
                      Habilitado
                    </label>
                    <button
                      className="ghost-button"
                      type="button"
                      onClick={() =>
                        setEmbeddingProfiles((current) =>
                          current.filter((_, position) => position !== index),
                        )
                      }
                      aria-label={`Quitar perfil ${profile.embedding_profile_id || index + 1}`}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))
              )}
            </div>
            <div className="ui-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() =>
                  setEmbeddingProfiles((current) => [
                    ...current,
                    { embedding_profile_id: "", enabled: true },
                  ])
                }
              >
                <Plus size={16} />
                Agregar perfil
              </button>
            </div>
          </fieldset>

          <div className="ui-actions">
            <button className="primary-button" type="submit" disabled={saving}>
              {saving ? <Loader2 className="spin" size={16} /> : <Save size={16} />}
              Guardar nueva versión
            </button>
          </div>
        </form>

        <section className="platform-bindings" aria-label="Bindings de target (solo lectura)">
          <span className="ui-field">Target bindings</span>
          {configuration.target_bindings.length === 0 ? (
            <p className="ui-field-note">Sin bindings provisionados por el servidor.</p>
          ) : (
            <div className="ui-status-row">
              {configuration.target_bindings.map((binding) => (
                <span className="ui-pill" key={binding.binding_key}>
                  {binding.binding_key} → {binding.embedding_profile_id}
                </span>
              ))}
            </div>
          )}
          <p className="ui-note">
            <Lock size={16} />
            <span>
              El target físico lo gestiona el servidor. Estos bindings son de solo lectura y no se
              editan desde la GUI.
            </span>
          </p>
        </section>
      </div>
    </section>
  );
}
