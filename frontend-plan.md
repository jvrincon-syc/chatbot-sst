# Frontend Work Plan

## 1. Analyze Current GUI
- Locate `frontend/src/components` and `frontend/src/pages`.
- Identify main view (`MainView`), inventory component, file‑review component, and any mismatch markers.
- Export component tree with `react‑tree‑wrapper` for reference.

## 2. Review & Audit
- Create a review checklist (`approve`, `disapprove`) for each component.
- Flag mismatches (incorrect props, missing data, OCR warnings) in a `review‑issues.json`.
- Generate a diff report comparing expected vs actual props.

## 3. Responsiveness Refactor
- Convert layout to CSS Grid / Flexbox with media‑query breakpoints.
- Ensure all components adapt to mobile, tablet, desktop widths.
- Add `responsive‑utils.ts` for shared breakpoints.

## 4. Expand Views
- Add missing inventory panel (`InventoryPanel`) linked to `DocumentViewer`.
- Add “Review Status” overlay showing approve/disapprove badges.
- Integrate pagination / infinite scroll for large file lists.

## 5. State Management
- Centralize UI state in `store.ts` (selected doc, view mode, filter tags).
- Provide selectors for current view (main, inventory, review) to avoid prop‑drilling.

## 6. Testing & Validation
- Write unit tests for responsive breakpoints (`@media` queries).
- Add e2e tests covering the full review workflow (approve → disapprove).
- Run `npm run lint && npm run typecheck` before committing.

## 7. Documentation
- Update `README.md` with new UI flow diagram.
- Add developer notes in `docs/frontend‑guide.md` about component responsibilities.