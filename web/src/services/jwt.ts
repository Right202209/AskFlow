import type { JWTPayload } from "@/types/auth";

export function decodeToken(token: string): JWTPayload {
  const payload = token.split(".")[1];
  if (!payload) throw new Error("Invalid token");
  const decoded = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
  return JSON.parse(decoded) as JWTPayload;
}

export function isTokenExpired(token: string): boolean {
  try {
    const payload = decodeToken(token);
    return Date.now() >= payload.exp * 1000;
  } catch {
    return true;
  }
}
