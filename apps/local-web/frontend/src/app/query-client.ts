// Input: 无  |  Output: 全局单例 QueryClient 实例
// Role: 配置 TanStack Query 全局缓存策略（staleTime=30s，关闭窗口聚焦刷新和自动重试）
// Note: staleTime 30s 适合本地低延迟 API；如需实时性可按 queryKey 覆盖
// Usage: import { queryClient } from "@/app/query-client"; 在 main.tsx 注入 Provider
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
});