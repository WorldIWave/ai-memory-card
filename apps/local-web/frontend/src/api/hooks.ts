// Input: TanStack Query + apiRequest  |  Output: useQuery/useMutation hooks for shared frontend data access
// Role: API data layer for decks, cards, imports, exports, and system workflows
// Note: useExportCards is disabled by default and should be triggered manually
// Usage: import { useDecks } from "@/api/hooks"; const { data } = useDecks();
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "./client";
import type {
  CardRead,
  DeckRead,
  ExportCardsResponse,
  ImportCardsResponse,
  SystemBackupRead,
  SystemDiagnosticsRead,
} from "./types";

export function useDecks(includeArchived = false) {
  return useQuery({
    queryKey: ["decks", includeArchived],
    queryFn: () =>
      apiRequest<DeckRead[]>(`/api/decks${includeArchived ? "?include_archived=true" : ""}`),
  });
}

export function useCards() {
  return useQuery({
    queryKey: ["cards"],
    queryFn: () => apiRequest<CardRead[]>("/api/cards"),
  });
}

export function useImportCards() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { format: string; content: string; deck_name?: string }) =>
      apiRequest<ImportCardsResponse>("/api/imports/cards", { method: "POST", body: payload }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["decks"] });
      void queryClient.invalidateQueries({ queryKey: ["cards"] });
    },
  });
}

export function useExportCards(format: "json" | "csv" | "markdown" = "json") {
  return useQuery({
    queryKey: ["exports", format],
    queryFn: () => apiRequest<ExportCardsResponse>(`/api/exports/cards?format=${format}`),
    enabled: false,
  });
}

export function useBackups() {
  return useQuery({
    queryKey: ["system", "backups"],
    queryFn: () => apiRequest<SystemBackupRead[]>("/api/system/backups"),
  });
}

export function useDiagnostics() {
  return useQuery({
    queryKey: ["system", "diagnostics"],
    queryFn: () => apiRequest<SystemDiagnosticsRead>("/api/system/diagnostics"),
  });
}
