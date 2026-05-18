// Input: 页面组件（ReviewPage、LibraryPage 等）  |  Output: react-router-dom 路由配置对象
// Role: 定义应用路由树，以 AppShell 为布局根，挂载四个主功能页及兜底重定向
// Note: 未匹配路径通过 Navigate 重定向到 /（复习页）；新增页面需在此注册
// Usage: import { router } from "@/app/router"; 在 main.tsx 传入 RouterProvider
import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./shell";
import { DataPage } from "../pages/data-page";
import { LibraryPage } from "../pages/library-page";
import { ReviewPage } from "../pages/review-page";
import { ReviewHistoryPage } from "../pages/review-history-page";
import { SettingsPage } from "../pages/settings-page";

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <ReviewPage /> },
      { path: "/library", element: <LibraryPage /> },
      { path: "/evaluation", element: <DataPage /> },
      { path: "/history", element: <ReviewHistoryPage /> },
      { path: "/settings", element: <SettingsPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
