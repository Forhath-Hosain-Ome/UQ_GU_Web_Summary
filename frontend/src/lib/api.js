import axios from "axios";
import { useAuthStore } from "../store/authStore";

const api = axios.create({ baseURL: "/api" });

// Attach access token to every request
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().access;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// On 401 → try to refresh; on failure → logout
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config;
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refresh = useAuthStore.getState().refresh;
      if (refresh) {
        try {
          const { data } = await axios.post("/api/auth/token/refresh/", { refresh });
          useAuthStore.getState().setAccess(data.access);
          original.headers.Authorization = `Bearer ${data.access}`;
          return api(original);
        } catch {
          useAuthStore.getState().logout();
        }
      } else {
        useAuthStore.getState().logout();
      }
    }
    return Promise.reject(err);
  }
);

export default api;
