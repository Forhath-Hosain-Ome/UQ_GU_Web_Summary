import final_summary_api from "../lib/final_summary_api";

// ── Upload ────────────────────────────────────────────────────────────────────
/**
 * POST /final-summary/upload/
 * Accepts one or many .xlsx/.xls files.
 * Returns { batch_id, total_files, files, ws_channel, message }
 */
export const uploadBatch = (files) => {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  return final_summary_api.post("upload/", fd).then((r) => r.data);
};

// ── Batches ───────────────────────────────────────────────────────────────────
export const fetchBatches = (params) =>
  final_summary_api.get("batches/", { params }).then((r) => r.data);

export const fetchBatch = (pk) =>
  final_summary_api.get(`batches/${pk}/`).then((r) => r.data);

// ── Logs ──────────────────────────────────────────────────────────────────────
/**
 * GET /final-summary/batches/<pk>/logs/
 * Returns structured error log: { batch_id, status, total_files, failed, errors: [...] }
 */
export const fetchBatchLogs = (pk) =>
  final_summary_api.get(`batches/${pk}/logs/`).then((r) => r.data);

/**
 * GET /final-summary/batches/<pk>/logs/error-json/
 * Returns a JSON payload the user can edit and POST to /retry/.
 * Shape: { version, batch_id, total_blocked, records: [...] }
 */
export const fetchErrorJson = (pk) =>
  final_summary_api.get(`batches/${pk}/logs/error-json/`).then((r) => r.data);

// ── Retry ─────────────────────────────────────────────────────────────────────
/**
 * POST /final-summary/retry/
 * Body: { batch_id: number, records: AuditRecord[] }
 * Returns { batch_id, submitted, saved, still_blocked: [...] }
 */
export const retryBatch = (batchId, records) =>
  final_summary_api
    .post("retry/", { batch_id: batchId, records })
    .then((r) => r.data);

// ── Export / Download ─────────────────────────────────────────────────────────
/**
 * GET /final-summary/export/
 * Required params: factory, client, date_from, date_to
 * Optional params: style, po
 * Returns .xlsx blob
 */
export const downloadSummary = (params) =>
  final_summary_api
    .get("export/", { params, responseType: "blob" })
    .then((r) => ({ blob: r.data, headers: r.headers }));

// ── Filter options (for export form dropdowns) ────────────────────────────────
/**
 * GET /final-summary/options/
 * Returns { factories, clients, min_date, max_date, styles, po_numbers }
 */
export const fetchFilterOptions = () =>
  final_summary_api.get("options/").then((r) => r.data);