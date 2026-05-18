// Input: 数字（字节数）或 ISO 时间字符串  |  Output: 人类可读的格式化字符串
// Role: 通用格式化工具，提供文件大小（B/KB/MB/GB）和时间戳的本地化显示
// Note: formatTimestamp 使用浏览器 Intl.DateTimeFormat，显示结果依赖用户系统语言
// Usage: import { formatBytes, formatTimestamp } from "@/utils/format";
export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB"];
  let current = value / 1024;
  let unitIndex = 0;
  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024;
    unitIndex += 1;
  }
  return `${current.toFixed(1)} ${units[unitIndex]}`;
}

export function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}
