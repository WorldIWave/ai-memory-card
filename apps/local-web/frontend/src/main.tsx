// Input: queryClient、router 配置  |  Output: React 应用挂载到 #root DOM 节点
// Role: 应用入口，组装 QueryClientProvider + RouterProvider 并启动渲染
// Note: 同时初始化 i18n 模块（副作用 import）；#root 缺失时立即抛出错误
// Usage: 由 Vite/Tauri 作为入口自动调用，不直接 import
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { queryClient } from "./app/query-client";
import { router } from "./app/router";
import "./styles.css";
import "./i18n/index";

const container = document.getElementById("root");

if (!container) {
  throw new Error('Root element with id "root" was not found.');
}

ReactDOM.createRoot(container).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>,
);