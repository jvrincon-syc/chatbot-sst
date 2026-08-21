import { useRef, useState, type FormEvent } from "react";
import { FileUp, Loader2, UploadCloud } from "lucide-react";

// Panel 1: alta de un documento RAW. El operador aporta el archivo y un
// source_relpath lógico/relativo (POSIX). El servidor calcula hash, tamaño y
// resuelve el target físico: aquí nada de eso cruza.
export function RawUploadPanel({
  disabled,
  uploading,
  lastUploadedRevisionId,
  onUpload,
}: {
  disabled: boolean;
  uploading: boolean;
  lastUploadedRevisionId: string | null;
  onUpload: (file: File, sourceRelpath: string) => Promise<boolean>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [sourceRelpath, setSourceRelpath] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const relpath = sourceRelpath.trim();
  const canSubmit = !disabled && !uploading && file !== null && relpath.length > 0;

  // Motivo visible del bloqueo del envío: nunca se deshabilita sin explicar.
  const reason = disabled
    ? "Selecciona un proyecto para subir documentos."
    : file === null
      ? "Elige un archivo para subir."
      : relpath.length === 0
        ? "Escribe la ruta lógica (source_relpath) del documento."
        : null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit || file === null) {
      return;
    }
    const ok = await onUpload(file, relpath);
    if (ok) {
      setFile(null);
      setSourceRelpath("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  return (
    <section className="panel" aria-label="Subir documento RAW">
      <div className="panel-heading">
        <div>
          <h2>Subir documento RAW</h2>
          <span>El servidor calcula hash y tamaño; tú solo aportas el archivo y su ruta lógica.</span>
        </div>
      </div>
      <div className="ui-panel-body">
        <form className="platform-create-form" onSubmit={handleSubmit}>
          <div className="ui-field">
            <label htmlFor="raw-file">Archivo</label>
            <input
              id="raw-file"
              ref={fileInputRef}
              type="file"
              disabled={disabled || uploading}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <span className="ui-field-note">PDF o Markdown del corpus del proyecto.</span>
          </div>
          <div className="ui-field">
            <label htmlFor="raw-relpath">Ruta lógica (source_relpath)</label>
            <input
              id="raw-relpath"
              value={sourceRelpath}
              placeholder="manuales/seguridad/procedimiento.pdf"
              autoComplete="off"
              disabled={disabled || uploading}
              onChange={(event) => setSourceRelpath(event.target.value)}
            />
            <span className="ui-field-note">
              Ruta relativa POSIX dentro del proyecto (sin rutas absolutas ni "..").
            </span>
          </div>
          <div className="ui-actions">
            <button className="primary-button" type="submit" disabled={!canSubmit}>
              {uploading ? <Loader2 className="spin" size={16} /> : <UploadCloud size={16} />}
              Subir documento
            </button>
          </div>
          {reason ? <span className="ui-field-note">{reason}</span> : null}
        </form>
        {lastUploadedRevisionId ? (
          <p className="ui-note">
            <FileUp size={16} />
            <span>
              Última revisión registrada: <strong>{lastUploadedRevisionId}</strong>
            </span>
          </p>
        ) : null}
      </div>
    </section>
  );
}
