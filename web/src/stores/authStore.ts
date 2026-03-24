import { create } from "zustand";
import { persist } from "zustand/middleware";
import { decodeToken, isTokenExpired } from "@/services/jwt";

interface AuthState {
  token: string | null;
  username: string | null;
  role: "user" | "agent" | "admin" | null;
  userId: string | null;

  login: (token: string, username: string) => void;
  logout: () => void;
  isAuthenticated: () => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
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

      isAuthenticated: () => {
        const { token } = get();
        if (!token) return false;
        return !isTokenExpired(token);
      },
    }),
    { name: "askflow-auth" },
  ),
);
