// Input: 请求 path、method、body、headers  |  Output: 泛型响应数据 TResponse
// Role: 全局 HTTP 客户端，统一处理 base URL 解析、错误抛出和 JSON 解析
// Note: 生产环境 base URL 由 window.__LMCA_BACKEND_URL__ 注入，开发回退到 127.0.0.1:8000
// Usage: import { apiRequest } from "./client"; apiRequest<T>("/api/...")
import type { ApiMethod } from "./types";

const defaultHeaders = {
  "Content-Type": "application/json",
};

function resolveUrl(path: string): string {
  if (!path.startsWith("/api")) return path;
  const base = (window as unknown as Record<string, unknown>)["__LMCA_BACKEND_URL__"];
  if (typeof base === "string") return base + path;
  // dev fallback: Vite proxy or direct backend
  return "http://127.0.0.1:8000" + path;
}

export async function apiRequest<TResponse>(
  path: string,
  options: {
    method?: ApiMethod;
    body?: unknown;
    headers?: HeadersInit;
    signal?: AbortSignal;
  } = {},
): Promise<TResponse> {
  const requestUrl = resolveUrl(path);
  const isFormData = options.body instanceof FormData;
  const requestBody: BodyInit | undefined =
    options.body === undefined ? undefined : isFormData ? (options.body as FormData) : JSON.stringify(options.body);
  let response: Response;
  try {
    response = await fetch(requestUrl, {
      method: options.method ?? "GET",
      headers: isFormData
        ? options.headers
        : {
            ...defaultHeaders,
            ...options.headers,
          },
      body: requestBody,
      signal: options.signal,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Request failed";
    throw new Error(`Network request failed for ${path}: ${message}`);
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // fall back to status-based error if payload is not JSON
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  return (await response.json()) as TResponse;
}
