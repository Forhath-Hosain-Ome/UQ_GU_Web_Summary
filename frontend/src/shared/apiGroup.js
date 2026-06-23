const PUMA_SECTION = [
  {
    label: "BATCHES",
    endpoints: [
      { id: "upload",       label: "Upload PDFs",      method: "POST", path: "/batches/upload/",     icon: "⬆" },
      { id: "batch-list",   label: "List Batches",     method: "GET",  path: "/batches/",            icon: "≡", action: "list",  listType: "batch" },
    ]
  },
];

const IMAGE_SECTIONS = [
  {
    label: "BATCHES",
    endpoints: [
      { id: "upload", label: "Upload Folders", method: "POST", path: "/folder/upload/", icon: "⬆" },
      { id: "batch-list", label: "List Batches", method: "GET", path: "/folder/batches/", icon: "≡", action: "list", listType: "batch" },
      { id: "batch-detail", label: "Batch Detail", method: "GET", path: "/folder/batches/{id}/", icon: "◎", action: "view" },
      { id: "batch-logs", label: "Batch Logs", method: "GET", path: "/folder/batches/{id}/logs/", icon: "∷", action: "logs" },
    ],
  },
  {
    label: "REPORTS",
    endpoints: [
      { id: "report-list", label: "List Reports", method: "GET", path: "/folder/reports/", icon: "≡", action: "list", listType: "report" },
      { id: "report-detail", label: "Report Detail", method: "GET", path: "/folder/reports/{id}/", icon: "◎", action: "view" },
      { id: "report-pdf", label: "Download PDF", method: "GET", path: "/folder/reports/{id}/pdf/", icon: "⬇", action: "pdf" },
      { id: "report-docx", label: "Download DOCX", method: "GET", path: "/folder/reports/{id}/docx/", icon: "⬇", action: "docx" },
    ],
  },
];


export const MENU_GROUPS = [
  {
    title: "PUMA",
    sections: PUMA_SECTION,
  },
  {
    title: "DEFECT_IMAGE",
    sections: IMAGE_SECTIONS,
  },
];