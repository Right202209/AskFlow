import { apiClient } from "./api";
import type { LoginRequest, LoginResponse, RegisterRequest } from "@/types/auth";

export async function login(data: LoginRequest): Promise<LoginResponse> {
  return apiClient<LoginResponse>("/api/v1/admin/auth/login", {
    method: "POST",
    body: JSON.stringify(data),
    skipUnauthorizedHandler: true,
  });
}

export async function register(data: RegisterRequest): Promise<void> {
  await apiClient<unknown>("/api/v1/admin/auth/register", {
    method: "POST",
    body: JSON.stringify(data),
    skipUnauthorizedHandler: true,
  });
}
