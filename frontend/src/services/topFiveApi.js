import top_five_api from "../lib/top_five_api";

// ── Jobs ──────────────────────────────────────────────────────────────────────
export const fetchJobs = (params) =>
  top_five_api.get("jobs/", { params }).then((r) => r.data);

export const fetchJob = (pk) =>
  top_five_api.get(`jobs/${pk}/`).then((r) => r.data);

export const uploadFile = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return top_five_api.post("upload/", fd).then((r) => r.data);
};

export const downloadResult = (pk) =>
  top_five_api
    .get(`jobs/${pk}/download/`, { responseType: "blob" })
    .then((r) => r.data);