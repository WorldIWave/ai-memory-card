// Input: vite.config 配置对象  |  Output: Vitest 测试套件（Node 环境）
// Role: 验证 Vite 开发服务器绑定到 127.0.0.1:5173 且使用严格端口，确保桌面壳兼容
// Note: 必须在 node 环境下运行（@vitest-environment node），不依赖 DOM
// Usage: Vitest 运行时自动发现，保障前后端端口约定不被意外修改
// @vitest-environment node

import { describe, expect, it } from "vitest";

import config from "../../vite.config";

describe("vite dev server config", () => {
  it("binds explicitly to the ipv4 loopback host used by the desktop shell", () => {
    expect(config.server?.host).toBe("127.0.0.1");
    expect(config.server?.port).toBe(5173);
    expect(config.server?.strictPort).toBe(true);
  });
});
