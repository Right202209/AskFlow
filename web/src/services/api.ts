import type { APIResponse } from "@/types/api";

let getToken: () => string | null = () => null;
let onUnauthorized: () => void = () => {};

export function configureApiClient(opts: {
  getToken: () => string | null;
  onUnauthorized: () => void;
}) {
  getToken = opts.getToken;
  onUnauthorized = opts.onUnauthorized;
}

export async function apiClient<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  if (
    !headers["Content-Type"] &&
    !(options?.body instanceof FormData)
  ) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(path, { ...options, headers });

  if (res.status === 401) {
    onUnauthorized();
    throw new Error("Unauthorized");
  }

  const json: APIResponse<T> = await res.json();

  if (!json.success) {
    throw new Error(json.error ?? "Request failed");
  }

  return json.data;
}
