export function PaginationBar({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  const canGoBack = page > 1;
  const canGoForward = totalPages > 0 && page < totalPages;
  return (
    <div className="ui-pagination">
      <button type="button" className="secondary-button" disabled={!canGoBack} onClick={() => onPageChange(page - 1)}>
        Anterior
      </button>
      <span>
        Pagina {page} de {totalPages || 0}
      </span>
      <button type="button" className="secondary-button" disabled={!canGoForward} onClick={() => onPageChange(page + 1)}>
        Siguiente
      </button>
    </div>
  );
}
