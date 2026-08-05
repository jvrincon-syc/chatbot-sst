export type SearchableDocumentReview = {
  sourceRelpath: string;
  documentId: string;
  documentName: string;
  ingestionProviderLabel: string;
  ingestionMethodLabel: string;
  reviewReasons: string[];
  reviewDetails: string[];
};

export function matchesDocumentReviewQuery(
  document: SearchableDocumentReview,
  rawQuery: string,
) {
  const needle = rawQuery.trim().toLowerCase();
  if (!needle) return true;
  return (
    document.sourceRelpath.toLowerCase().includes(needle) ||
    document.documentId.toLowerCase().includes(needle) ||
    document.documentName.toLowerCase().includes(needle) ||
    document.ingestionProviderLabel.toLowerCase().includes(needle) ||
    document.ingestionMethodLabel.toLowerCase().includes(needle) ||
    document.reviewReasons.some((reason) => reason.toLowerCase().includes(needle)) ||
    document.reviewDetails.some((detail) => detail.toLowerCase().includes(needle))
  );
}
