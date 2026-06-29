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
};

export const linklensApi = {
  startSearch: (data: any) => api.post("/api/linklens/search", data).then((r) => r.data),
  listSearches: () => api.get("/api/linklens/searches").then((r) => r.data),
  getSearch: (id: number) => api.get(`/api/linklens/searches/${id}`).then((r) => r.data),
  exportProfiles: (id: number) =>
    api.get(`/api/linklens/searches/${id}/export`, { responseType: "blob" }).then((r) => r.data),
};

export const dashboardApi = {
  getStats: () => api.get("/api/dashboard/stats").then((r) => r.data),
};

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
