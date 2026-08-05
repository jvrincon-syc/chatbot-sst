import { Check, FileText, ListFilter, Loader2, Search, UploadCloud, X } from "lucide-react";
import type { DecisionKind, DocumentRecord, DisplayStatus, ReviewStatus } from "../dashboardTypes";

export function ReviewWorkspace({
  documents,
  busyAction,
  notes,
  selectedDocument,
  selectedDocumentId,
  onSelect,
  onNoteChange,
  onReview,
}: {
  documents: DocumentRecord[];
  busyAction: string | null;
  notes: Record<string, string>;
  selectedDocument: DocumentRecord | null;
  selectedDocumentId: string | null;
  onSelect: (document: DocumentRecord) => void;
  onNoteChange: (documentId: string, value: string) => void;
  onReview: (document: DocumentRecord, decision: DecisionKind) => void;
}) {
  return (
    <section className="review-workspace">
      <PendingReviewPanel
        documents={documents}
        busyAction={busyAction}
        notes={notes}
        selectedDocumentId={selectedDocumentId}
        onSelect={onSelect}
        onNoteChange={onNoteChange}
        onReview={onReview}
      />
      <DocumentInspector
        document={selectedDocument}
        contextLabel="Vista de revisión"
        busyAction={busyAction}
        note={selectedDocument ? notes[selectedDocument.documentId] ?? "" : ""}
        onNoteChange={(value) => {
          if (selectedDocument) {
            onNoteChange(selectedDocument.documentId, value);
          }
        }}
        onReview={onReview}
      />
    </section>
  );
}

export function InventoryWorkspace({
  documents,
  total,
  query,
  statusFilter,
  ingestionFilter,
  ingestionMethodOptions,
  selectedDocument,
  selectedDocumentId,
  onSelect,
  onQueryChange,
  onStatusFilterChange,
  onIngestionFilterChange,
}: {
  documents: DocumentRecord[];
  total: number;
  query: string;
  statusFilter: string;
  ingestionFilter: string;
  ingestionMethodOptions: { value: string; label: string }[];
  selectedDocument: DocumentRecord | null;
  selectedDocumentId: string | null;
  onSelect: (document: DocumentRecord) => void;
  onQueryChange: (value: string) => void;
  onStatusFilterChange: (value: string) => void;
  onIngestionFilterChange: (value: string) => void;
}) {
  return (
    <section className="inventory-workspace">
      <InventoryPanel
        documents={documents}
        total={total}
        query={query}
        statusFilter={statusFilter}
        ingestionFilter={ingestionFilter}
        ingestionMethodOptions={ingestionMethodOptions}
        selectedDocumentId={selectedDocumentId}
        onSelect={onSelect}
        onQueryChange={onQueryChange}
        onStatusFilterChange={onStatusFilterChange}
        onIngestionFilterChange={onIngestionFilterChange}
      />
      <DocumentInspector
        document={selectedDocument}
        contextLabel="Inventario normalizado"
        busyAction={null}
        note=""
        onNoteChange={() => undefined}
        onReview={() => undefined}
      />
    </section>
  );
}

function PendingReviewPanel({
  documents,
  busyAction,
  notes,
  selectedDocumentId,
  onSelect,
  onNoteChange,
  onReview,
}: {
  documents: DocumentRecord[];
  busyAction: string | null;
  notes: Record<string, string>;
  selectedDocumentId: string | null;
  onSelect: (document: DocumentRecord) => void;
  onNoteChange: (documentId: string, value: string) => void;
  onReview: (document: DocumentRecord, decision: DecisionKind) => void;
}) {
  return (
    <section className="panel review-panel">
      <div className="panel-heading">
        <h2>Documentos en revisión</h2>
        <span>{documents.length} pendientes</span>
      </div>
      <div className="table-wrap compact">
        <table>
          <thead>
            <tr>
              <th>Documento</th>
              <th>Categoría</th>
              <th>Motivos</th>
              <th>Decisión</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr
                className={selectedDocumentId === document.documentId ? "selected-row" : ""}
                key={document.documentId}
              >
                <td>
                  <div className="doc-cell">
                    <FileText size={15} />
                    <span>{document.documentName}</span>
                    <small>{document.sourceRelpath}</small>
                    <button
                      className="row-detail-button"
                      onClick={() => onSelect(document)}
                      type="button"
                    >
                      Ver detalle
                    </button>
                  </div>
                </td>
                <td>{document.category}</td>
                <td>
                  <ReasonList reasons={document.reviewReasons} />
                </td>
                <td className="review-actions">
                  <textarea
                    aria-label={`Motivo para ${document.documentName}`}
                    value={notes[document.documentId] ?? ""}
                    placeholder="Motivo de revisión"
                    onChange={(event) => onNoteChange(document.documentId, event.target.value)}
                  />
                  <div>
                    <button
                      className="approve-button"
                      disabled={busyAction === `approved:${document.documentId}`}
                      onClick={() => onReview(document, "approved")}
                      type="button"
                    >
                      <Check size={15} />
                      Aprobar
                    </button>
                    <button
                      className="reject-button"
                      disabled={busyAction === `rejected:${document.documentId}`}
                      onClick={() => onReview(document, "rejected")}
                      type="button"
                    >
                      <X size={15} />
                      Rechazar
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {documents.length === 0 ? (
              <tr>
                <td colSpan={4} className="empty-cell">
                  Sin documentos pendientes de decisión.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function InventoryPanel({
  documents,
  total,
  query,
  statusFilter,
  ingestionFilter,
  ingestionMethodOptions,
  selectedDocumentId,
  onSelect,
  onQueryChange,
  onStatusFilterChange,
  onIngestionFilterChange,
}: {
  documents: DocumentRecord[];
  total: number;
  query: string;
  statusFilter: string;
  ingestionFilter: string;
  ingestionMethodOptions: { value: string; label: string }[];
  selectedDocumentId: string | null;
  onSelect: (document: DocumentRecord) => void;
  onQueryChange: (value: string) => void;
  onStatusFilterChange: (value: string) => void;
  onIngestionFilterChange: (value: string) => void;
}) {
  return (
    <section className="panel inventory-panel">
      <div className="panel-heading inventory-heading">
        <div>
          <h2>Inventario</h2>
          <span>
            {documents.length} de {total}
          </span>
        </div>
        <div className="inventory-tools">
          <label className="search-field">
            <Search size={16} />
            <input
              value={query}
              placeholder="Buscar documento"
              onChange={(event) => onQueryChange(event.target.value)}
            />
          </label>
          <label className="filter-field">
            <ListFilter size={16} />
            <select
              value={statusFilter}
              onChange={(event) => onStatusFilterChange(event.target.value)}
            >
              <option value="all">Todos</option>
              <option value="processed">Procesados</option>
              <option value="needs_review">En revisión</option>
              <option value="failed">Fallidos</option>
              <option value="approved">Aprobados</option>
              <option value="rejected">Rechazados</option>
            </select>
          </label>
          <label className="filter-field">
            <UploadCloud size={16} />
            <select
              value={ingestionFilter}
              onChange={(event) => onIngestionFilterChange(event.target.value)}
              aria-label="Filtrar por ingesta"
            >
              <option value="all">Toda ingesta</option>
              <optgroup label="Proveedor">
                <option value="provider:local">Local</option>
                <option value="provider:llama_cloud">Llama</option>
                <option value="provider:unregistered">Sin ingesta</option>
              </optgroup>
              {ingestionMethodOptions.length > 0 ? (
                <optgroup label="Método">
                  {ingestionMethodOptions.map((option) => (
                    <option value={option.value} key={option.value}>
                      {option.label}
                    </option>
                  ))}
                </optgroup>
              ) : null}
            </select>
          </label>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ruta del documento</th>
              <th>Tipo</th>
              <th>Ingesta</th>
              <th>Confiabilidad</th>
              <th>Categoría</th>
              <th>Tamaño</th>
              <th>Estado</th>
              <th>Decisión de revisión</th>
              <th>Fecha</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((document) => (
              <tr
                className={selectedDocumentId === document.documentId ? "selected-row" : ""}
                key={document.documentId}
              >
                <td>
                  <div className="doc-cell">
                    <FileText size={15} />
                    <span>{document.sourceRelpath}</span>
                    <small>{document.documentId}</small>
                    <button
                      className="row-detail-button"
                      onClick={() => onSelect(document)}
                      type="button"
                    >
                      Revisar evidencia
                    </button>
                  </div>
                </td>
                <td>{document.detectedExtension?.replace(".", "").toUpperCase() ?? "N/D"}</td>
                <td>
                  <IngestionChip document={document} />
                </td>
                <td>
                  <ConfidenceChip document={document} />
                </td>
                <td>{document.category}</td>
                <td>{formatBytes(document.fileSize)}</td>
                <td>
                  <StatusChip status={document.displayStatus} />
                </td>
                <td>
                  <DecisionChip reviewStatus={document.reviewStatus} />
                </td>
                <td>{formatDate(document.ingestionDate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {documents.length === 0 ? (
          <div className="empty-cell">No hay documentos con los filtros actuales.</div>
        ) : null}
      </div>
    </section>
  );
}

function DocumentInspector({
  document,
  contextLabel,
  busyAction,
  note,
  onNoteChange,
  onReview,
}: {
  document: DocumentRecord | null;
  contextLabel: string;
  busyAction: string | null;
  note: string;
  onNoteChange: (value: string) => void;
  onReview: (document: DocumentRecord, decision: DecisionKind) => void;
}) {
  if (!document) {
    return (
      <aside className="panel document-inspector">
        <div className="panel-heading inspector-heading">
          <div>
            <h2>Detalle de documento</h2>
            <span>{contextLabel}</span>
          </div>
        </div>
        <div className="inspector-empty">
          <FileText size={28} />
          <span>Selecciona un documento para revisar rutas, motivos y decisiones.</span>
        </div>
      </aside>
    );
  }

  const canReview = document.processingStatus === "needs_review";
  const approveBusy = busyAction === `approved:${document.documentId}`;
  const rejectBusy = busyAction === `rejected:${document.documentId}`;

  return (
    <aside className="panel document-inspector">
      <div className="panel-heading inspector-heading">
        <div>
          <h2>Detalle de documento</h2>
          <span>{contextLabel}</span>
        </div>
        <DecisionChip reviewStatus={document.reviewStatus} />
      </div>
      <div className="inspector-body">
        <div className="inspector-title">
          <FileText size={18} />
          <div>
            <strong>{document.documentName}</strong>
            <span>{document.sourceRelpath}</span>
          </div>
        </div>

        <dl className="metadata-grid">
          <div>
            <dt>Document ID</dt>
            <dd>{document.documentId}</dd>
          </div>
          <div>
            <dt>Categoría</dt>
            <dd>{document.category ?? "N/D"}</dd>
          </div>
          <div>
            <dt>Tipo</dt>
            <dd>{document.detectedExtension?.replace(".", "").toUpperCase() ?? "N/D"}</dd>
          </div>
          <div>
            <dt>Tamaño</dt>
            <dd>{formatBytes(document.fileSize)}</dd>
          </div>
          <div>
            <dt>Ingesta</dt>
            <dd>{document.ingestionProviderLabel}</dd>
          </div>
          <div>
            <dt>Método</dt>
            <dd>{document.ingestionMethodLabel}</dd>
          </div>
          <div>
            <dt>OCR</dt>
            <dd>{document.ocrConfidenceLabel}</dd>
          </div>
          <div>
            <dt>Fecha</dt>
            <dd>{formatDate(document.ingestionDate)}</dd>
          </div>
        </dl>

        <section className="inspector-section">
          <h3>Motivos de revisión</h3>
          <ReasonList reasons={document.reviewReasons} />
        </section>

        <section className="inspector-section">
          <h3>Detalles auditables</h3>
          {document.reviewDetails.length > 0 ? (
            <ul className="detail-list">
              {document.reviewDetails.map((detail) => (
                <li key={detail}>{detail}</li>
              ))}
            </ul>
          ) : (
            <span className="muted">Sin detalles adicionales.</span>
          )}
        </section>

        {document.decision ? (
          <section className="decision-summary">
            <h3>Decisión registrada</h3>
            <p>{document.decision.reason}</p>
            <small>{formatDate(document.decision.decided_at)}</small>
          </section>
        ) : null}

        {canReview ? (
          <section className="inspector-section">
            <label className="inspector-note">
              Motivo de decisión
              <textarea
                aria-label={`Motivo para ${document.documentName}`}
                onChange={(event) => onNoteChange(event.target.value)}
                placeholder="Describe por qué se aprueba o se rechaza"
                value={note}
              />
            </label>
            <div className="inspector-actions">
              <button
                className="approve-button"
                disabled={approveBusy || rejectBusy}
                onClick={() => onReview(document, "approved")}
                type="button"
              >
                {approveBusy ? <Loader2 className="spin" size={15} /> : <Check size={15} />}
                Aprobar
              </button>
              <button
                className="reject-button"
                disabled={approveBusy || rejectBusy}
                onClick={() => onReview(document, "rejected")}
                type="button"
              >
                {rejectBusy ? <Loader2 className="spin" size={15} /> : <X size={15} />}
                Rechazar
              </button>
            </div>
          </section>
        ) : (
          <section className="inspector-section">
            <span className="muted">Este documento no requiere decisión manual.</span>
          </section>
        )}
      </div>
    </aside>
  );
}

function IngestionChip({ document }: { document: DocumentRecord }) {
  return (
    <div className="ingestion-cell">
      <span className={`chip ingestion-${document.ingestionProvider}`}>
        {document.ingestionProviderLabel}
      </span>
      <small>{document.ingestionMethodLabel}</small>
    </div>
  );
}

function ConfidenceChip({ document }: { document: DocumentRecord }) {
  const hasValue = document.ocrConfidencePercent !== null;
  return (
    <div className="confidence-cell">
      <span className={hasValue ? "chip confidence-value" : "chip confidence-na"}>
        {document.ocrConfidenceLabel}
      </span>
      <small>{document.ocrConfidenceKind}</small>
    </div>
  );
}

function ReasonList({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) {
    return <span className="muted">Sin motivos</span>;
  }
  return (
    <div className="reason-list">
      {reasons.map((reason) => (
        <span key={reason}>{reason}</span>
      ))}
    </div>
  );
}

function StatusChip({ status }: { status: DisplayStatus }) {
  return <span className={`chip status-${status}`}>{statusLabels[status]}</span>;
}

function DecisionChip({ reviewStatus }: { reviewStatus: ReviewStatus }) {
  if (reviewStatus === "not_required") {
    return <span className="chip neutral">No aplica</span>;
  }
  if (reviewStatus === "pending") {
    return <span className="chip neutral">Pendiente</span>;
  }
  return (
    <span className={`chip decision-${reviewStatus}`}>
      {reviewStatus === "approved" ? "Aprobado" : "Rechazado"}
    </span>
  );
}

function formatBytes(value: number) {
  if (!Number.isFinite(value)) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

function formatDate(value: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("es-CO", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

const statusLabels: Record<DisplayStatus, string> = {
  pending: "Pendiente",
  processed: "Procesado",
  failed: "Fallido",
  needs_review: "En revisión",
  approved: "Aprobado",
  rejected: "Rechazado",
};
