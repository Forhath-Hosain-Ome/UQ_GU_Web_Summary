import { create } from "zustand";
import { persist } from "zustand/middleware";
import { jwtDecode } from "jwt-decode";

export const useAuthStore = create(
  persist(
    (set, get) => ({
      access: null,
      refresh: null,
      user: null,

      login: (access, refresh) => {
        let user = null;
        try { user = jwtDecode(access); } catch {}
        set({ access, refresh, user });
      },

      logout: () => set({ access: null, refresh: null, user: null }),

      setAccess: (access) => {
        let user = null;
        try { user = jwtDecode(access); } catch {}
        set({ access, user });
      },

      isAuthenticated: () => {
        const { access } = get();
        if (!access) return false;
        try {
          const { exp } = jwtDecode(access);
          return Date.now() / 1000 < exp;
        } catch { return false; }
      },
    }),
    { name: "qc-auth", partialize: (s) => ({ access: s.access, refresh: s.refresh }) }
  )
);
