import { apiRequest } from "./client";
import type { PluginConfigRead, PluginConfigUpdateInput, PluginStatusRead } from "./types";

export function getRagPluginStatus() {
  return apiRequest<PluginStatusRead>("/api/ai/plugins/rag-core");
}

export function updateRagPluginConfig(body: PluginConfigUpdateInput) {
  return apiRequest<PluginConfigRead>("/api/ai/plugins/rag-core/config", {
    method: "PUT",
    body,
  });
}

export function testRagPlugin() {
  return apiRequest<PluginStatusRead>("/api/ai/plugins/rag-core/test", {
    method: "POST",
  });
}
