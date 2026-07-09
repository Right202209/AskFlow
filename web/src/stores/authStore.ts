import { create } from "zustand";
import { persist } from "zustand/middleware";
import { decodeToken } from "@/services/jwt";

interface AuthState {
  token: string | null;
  username: string | null;
  role: "user" | "agent" | "admin" | null;
  userId: string | null;

  login: (token: string, username: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      role: null,
      userId: null,

      login: (token, username) => {
        const payload = decodeToken(token);
        set({
          token,
          username,
          role: payload.role,
          userId: payload.sub,
        });
      },

      logout: () => {
        set({ token: null, username: null, role: null, userId: null });
      },
    }),
    { name: "askflow-auth" },
  ),
);
