import image_api from "../lib/image_api";

const normalizeReport = (report) => ({
  ...report,
  style: report.style || report.folder_name || report.report_number || "",
});

const normalizeReportPayload = (payload) => {
  if (payload == null) return payload;
  if (Array.isArray(payload.results)) {
    return {
      ...payload,
      results: payload.results.map(normalizeReport),
    };
  }
  return normalizeReport(payload);
};

const normalizeBatch = (batch) => ({
  ...batch,
  reports: batch.reports?.map(normalizeReport) || batch.reports,
});

// ── Batches ───────────────────────────────────────────────────────────────────
export const fetchBatches = (params) =>
  image_api.get("folder/batches/", { params }).then((r) => r.data);

export const fetchBatch = (pk) =>
  image_api.get(`folder/batches/${pk}/`).then((r) => normalizeBatch(r.data));

export const uploadBatch = (files, paths = [], date = null, style = "") => {
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  paths.forEach((path) => fd.append("paths", path));
  if (date) fd.append("date", date);
  if (style) fd.append("style", style);
  return image_api.post("folder/upload/", fd).then((r) => r.data);
};

export const fetchBatchLogs = (pk) =>
  image_api.get(`folder/batches/${pk}/logs/`).then((r) => r.data);

// ── Reports ───────────────────────────────────────────────────────────────────
export const fetchReports = (params) =>
  image_api.get("folder/reports/", { params }).then((r) => normalizeReportPayload(r.data));

export const fetchReport = (pk) =>
  image_api.get(`folder/reports/${pk}/`).then((r) => normalizeReport(r.data));

export const downloadReportPDF = (pk) =>
  image_api.get(`folder/reports/${pk}/pdf/`, { responseType: "blob" }).then((r) => r.data);

export const downloadReportDOCX = (pk) =>
  image_api.get(`folder/reports/${pk}/docx/`, { responseType: "blob" }).then((r) => r.data);