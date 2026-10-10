import { request } from "./client";
import type { LoginInput, LoginResult } from "./types";

const useMocks = import.meta.env.VITE_USE_MOCKS !== "false";

export async function login(input: LoginInput): Promise<LoginResult> {
  if (useMocks) {
    await new Promise((resolve) => window.setTimeout(resolve, 350));
    return { user: { id: "user-demo", name: "顾工程师", email: input.email, role: "项目管理员" }, accessToken: "mock-token" };
  }
  return request<LoginResult>("/api/v1/auth/login", { method: "POST", body: JSON.stringify(input) });
}

export async function logout(): Promise<void> {
  if (useMocks) return;
  await request<void>("/api/v1/auth/logout", { method: "POST" });
}
