import { create } from "zustand";

export type ToastVariant = "success" | "error" | "info";

export interface ToastItem {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface ToastInput {
  title: string;
  description?: string;
  variant?: ToastVariant;
  durationMs?: number;
}

interface ToastState {
  toasts: ToastItem[];
  showToast: (input: ToastInput) => string;
  dismissToast: (id: string) => void;
  clearToasts: () => void;
}

const DEFAULT_DURATION_MS = 4000;

export const useToastStore = create<ToastState>()((set) => ({
  toasts: [],

  showToast: ({ title, description, variant = "info", durationMs = DEFAULT_DURATION_MS }) => {
    const id = crypto.randomUUID();

    set((state) => ({
      toasts: [...state.toasts, { id, title, description, variant }],
    }));

    globalThis.setTimeout(() => {
      set((state) => ({
        toasts: state.toasts.filter((toast) => toast.id !== id),
      }));
    }, durationMs);

    return id;
  },

  dismissToast: (id) =>
    set((state) => ({
      toasts: state.toasts.filter((toast) => toast.id !== id),
    })),

  clearToasts: () => set({ toasts: [] }),
}));

export function toastSuccess(title: string, description?: string) {
  return useToastStore.getState().showToast({ title, description, variant: "success" });
}

export function toastError(title: string, description?: string) {
  return useToastStore.getState().showToast({ title, description, variant: "error" });
}

export function toastInfo(title: string, description?: string) {
  return useToastStore.getState().showToast({ title, description, variant: "info" });
}
