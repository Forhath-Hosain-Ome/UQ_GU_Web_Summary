import { create } from "zustand";

export const useOutputStore = create((set, get) => ({
  // Current output shown in the right panel
  output: null,        // { type: "batch"|"report"|"logs"|"excel", data: any, action?: string }
  outputTitle: "",
  isLoading: false,

  // Activity log entries shown in the left panel
  logs: [],

  setOutput: (type, data, title = "", meta = {}) =>
    set({ output: { type, data, ...meta }, outputTitle: title, isLoading: false }),

  setLoading: (v) => set({ isLoading: v }),

  clearOutput: () => set({ output: null, outputTitle: "", isLoading: false }),

  addLog: (entry) =>
    set((s) => ({
      logs: [{ id: Date.now(), ts: new Date().toISOString(), ...entry }, ...s.logs].slice(0, 200),
    })),

  clearLogs: () => set({ logs: [] }),
}));
