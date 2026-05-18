// Input: 任意数量的 ClassValue（字符串/对象/数组）  |  Output: 合并去重后的 Tailwind class 字符串
// Role: 全局 className 工具函数，组合 clsx 条件拼接与 tailwind-merge 冲突消除
// Note: 所有组件的动态 class 拼接应统一使用 cn()，避免 Tailwind 类名冲突
// Usage: import { cn } from "@/lib/utils"; cn("px-2", isActive && "bg-accent")
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
