import axios from "axios";

// Use relative /api — Vite proxies to http://localhost:8000, bypassing CORS
export const api = axios.create({
  baseURL: "",
  timeout: 60_000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("talentiq_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("talentiq_token");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export const authApi = {
  register: (data: any) => api.post("/api/auth/register", data).then((r) => r.data),
  login: (data: any) => api.post("/api/auth/login", data).then((r) => r.data),
  me: () => api.get("/api/auth/me").then((r) => r.data),
  updateProfile: (data: any) => api.put("/api/auth/me", data).then((r) => r.data),
  changePassword: (old_pw: string, new_pw: string) =>
    api.post(`/api/auth/change-password?old_password=${encodeURIComponent(old_pw)}&new_password=${encodeURIComponent(new_pw)}`).then((r) => r.data),
  listApiKeys: () => api.get("/api/auth/api-keys").then((r) => r.data),
  listGlobalKeys: () => api.get("/api/auth/global-keys").then((r) => r.data),
  saveApiKey: (data: any) => api.post("/api/auth/api-keys", data).then((r) => r.data),
  deleteApiKey: (id: number) => api.delete(`/api/auth/api-keys/${id}`).then((r) => r.data),
  listUsers: () => api.get("/api/auth/users").then((r) => r.data),
  deactivateUser: (id: number) => api.put(`/api/auth/users/${id}/deactivate`).then((r) => r.data),
};

export const jobhuntApi = {
  uploadResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/api/jobhunt/resume", form).then((r) => r.data);
  },
  listResumes: () => api.get("/api/jobhunt/resumes").then((r) => r.data),
  searchJobs: (data: any) => api.post("/api/jobhunt/search", data).then((r) => r.data),
  listSearches: () => api.get("/api/jobhunt/searches").then((r) => r.data),
  deleteSearch: (id: number) => api.delete(`/api/jobhunt/searches/${id}`).then((r) => r.data),
  deleteAllSearches: () => api.delete("/api/jobhunt/searches").then((r) => r.data),
  matchResume: (data: any) => api.post("/api/jobhunt/match", data).then((r) => r.data),
  listMatches: () => api.get("/api/jobhunt/matches").then((r) => r.data),
  exportExcel: (searchId: number) =>
    api.get(`/api/jobhunt/export/${searchId}`, { responseType: "blob" }).then((r) => r.data),
};

export const jobintelApi = {
  runAnalysis: (data: any) => api.post("/api/jobintel/run", data).then((r) => r.data),
  listRuns: () => api.get("/api/jobintel/runs").then((r) => r.data),
  getRun: (id: number) => api.get(`/api/jobintel/runs/${id}`).then((r) => r.data),
  getRunRecords: (id: number) => api.get(`/api/jobintel/runs/${id}/records`).then((r) => r.data),
  deleteRun: (id: number) => api.delete(`/api/jobintel/runs/${id}`).then((r) => r.data),
  deleteAllRuns: () => api.delete("/api/jobintel/runs").then((r) => r.data),
};

export const linklensApi = {
  startSearch: (data: any) => api.post("/api/linklens/search", data).then((r) => r.data),
  listSearches: () => api.get("/api/linklens/searches").then((r) => r.data),
  getSearch: (id: number) => api.get(`/api/linklens/searches/${id}`).then((r) => r.data),
  deleteSearch: (id: number) => api.delete(`/api/linklens/searches/${id}`).then((r) => r.data),
  deleteAllSearches: () => api.delete("/api/linklens/searches").then(r => r.data),
  exportProfiles: (id: number) =>
    api.get(`/api/linklens/searches/${id}/export`, { responseType: "blob" }).then((r) => r.data),
};

export const dashboardApi = {
  getStats: () => api.get("/api/dashboard/stats").then((r) => r.data),
  jobHunterSummary: () => api.get("/api/dashboard/jobhunter-summary").then((r) => r.data),
  marketIntelSummary: () => api.get("/api/dashboard/marketintel-summary").then((r) => r.data),
  linkExploreSummary: () => api.get("/api/dashboard/linkexplore-summary").then((r) => r.data),
};

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const joblensApi = {
  deleteSession: (id: number) => api.delete(`/api/joblens/sessions/${id}`).then(r => r.data),
  deleteAllSessions: () => api.delete("/api/joblens/sessions").then(r => r.data),
};

export const jdcreatorApi = {
  generate: (data: any) => api.post("/api/jdcreator/generate", data).then(r => r.data),
  listDocuments: () => api.get("/api/jdcreator/documents").then(r => r.data),
  getDocument: (id: number) => api.get(`/api/jdcreator/documents/${id}`).then(r => r.data),
  deleteDocument: (id: number) => api.delete(`/api/jdcreator/documents/${id}`).then(r => r.data),
  download: (id: number) =>
    api.get(`/api/jdcreator/documents/${id}/download`, { responseType: "blob" }).then(r => r.data),
};

export const cvintelApi = {
  saveHistory: (data: any) => api.post("/api/cvintel/history", data).then(r => r.data),
  listHistory: () => api.get("/api/cvintel/history").then(r => r.data),
  deleteHistoryItem: (id: number) => api.delete(`/api/cvintel/history/${id}`).then(r => r.data),
  deleteAllHistory: () => api.delete("/api/cvintel/history").then(r => r.data),
};

export const candidateTrackApi = {
  meta: () => api.get("/api/candidatetrack/meta").then(r => r.data),

  listClients: () => api.get("/api/candidatetrack/clients").then(r => r.data),
  createClient: (data: any) => api.post("/api/candidatetrack/clients", data).then(r => r.data),
  updateClient: (id: number, data: any) => api.put(`/api/candidatetrack/clients/${id}`, data).then(r => r.data),
  deleteClient: (id: number) => api.delete(`/api/candidatetrack/clients/${id}`).then(r => r.data),
  bulkDeleteClients: (ids: number[]) => api.delete("/api/candidatetrack/clients", { data: { ids } }).then(r => r.data),
  importClientsCsv: (form: FormData) => api.post("/api/candidatetrack/clients/import-csv", form, { headers: { "Content-Type": "multipart/form-data" } }).then(r => r.data),

  listJDs: () => api.get("/api/candidatetrack/jds").then(r => r.data),
  jdStats: () => api.get("/api/candidatetrack/jds/stats").then(r => r.data),
  jdDashboardSummary: () => api.get("/api/candidatetrack/dashboard/jd-summary").then(r => r.data),
  vendorDashboardSummary: () => api.get("/api/candidatetrack/dashboard/vendor-summary").then(r => r.data),
  createJD: (data: any) => api.post("/api/candidatetrack/jds", data).then(r => r.data),
  updateJD: (id: number, data: any) => api.put(`/api/candidatetrack/jds/${id}`, data).then(r => r.data),
  deleteJD: (id: number) => api.delete(`/api/candidatetrack/jds/${id}`).then(r => r.data),
  bulkDeleteJDs: (ids: number[]) => api.delete("/api/candidatetrack/jds", { data: { ids } }).then(r => r.data),
  importJDsCsv: (form: FormData) => api.post("/api/candidatetrack/jds/import-csv", form, { headers: { "Content-Type": "multipart/form-data" } }).then(r => r.data),
  uploadJDFile: (jdId: number, form: FormData) => api.post(`/api/candidatetrack/jds/${jdId}/file`, form, { headers: { "Content-Type": "multipart/form-data" } }).then(r => r.data),

  listVendors: () => api.get("/api/candidatetrack/vendors").then(r => r.data),
  createVendor: (data: any) => api.post("/api/candidatetrack/vendors", data).then(r => r.data),
  updateVendor: (id: number, data: any) => api.put(`/api/candidatetrack/vendors/${id}`, data).then(r => r.data),
  deleteVendor: (id: number) => api.delete(`/api/candidatetrack/vendors/${id}`).then(r => r.data),
  bulkDeleteVendors: (ids: number[]) => api.delete("/api/candidatetrack/vendors", { data: { ids } }).then(r => r.data),
  importVendorsCsv: (form: FormData) => api.post("/api/candidatetrack/vendors/import-csv", form, { headers: { "Content-Type": "multipart/form-data" } }).then(r => r.data),

  listCandidates: () => api.get("/api/candidatetrack/candidates").then(r => r.data),
  createCandidate: (form: FormData) =>
    api.post("/api/candidatetrack/candidates", form, { headers: { "Content-Type": "multipart/form-data" } }).then(r => r.data),
  bulkUploadCandidates: (form: FormData) =>
    api.post("/api/candidatetrack/candidates/bulk-upload", form, { headers: { "Content-Type": "multipart/form-data" } }).then(r => r.data),
  updateCandidate: (id: number, data: any) => api.put(`/api/candidatetrack/candidates/${id}`, data).then(r => r.data),
  deleteCandidate: (id: number) => api.delete(`/api/candidatetrack/candidates/${id}`).then(r => r.data),
  bulkDeleteCandidates: (ids: number[]) => api.delete("/api/candidatetrack/candidates", { data: { ids } }).then(r => r.data),
  candidateStatusLog: (id: number) => api.get(`/api/candidatetrack/candidates/${id}/status-log`).then(r => r.data),
};