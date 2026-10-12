import { request } from "./client";
import type { LoginInput, LoginResult } from "./types";

export async function login(input: LoginInput): Promise<LoginResult> {
  return request<LoginResult>("/api/v1/auth/login", { method: "POST", body: JSON.stringify(input) });
}

export async function logout(): Promise<void> {
  await request<void>("/api/v1/auth/logout", { method: "POST" });
}
