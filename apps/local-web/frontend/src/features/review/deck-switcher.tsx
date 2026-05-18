/**
 * Input: ???????????????  |  Output: ?????????
 * Output: ? review ???? deck ??? session ????
 * Role: ?? review ????????????
 * Use: ?????????? session????????????
 */
import * as Popover from "@radix-ui/react-popover";
import { ChevronDown, Layers } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { DeckRead } from "../../api/types";
import { Badge, Button } from "../../components/ui";
import { cn } from "../../lib/utils";

interface DeckSwitcherProps {
  decks: DeckRead[];
  selectedDeckId: number | null;
  onSelect: (deckId: number | null) => void;
}

export function DeckSwitcher({ decks, selectedDeckId, onSelect }: DeckSwitcherProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const selected = decks.find((d) => d.id === selectedDeckId);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button variant="secondary" className="review-deck-trigger">
          <Layers size={16} aria-hidden="true" />
          <span>{selected?.name ?? t("review_all_decks")}</span>
          <ChevronDown size={14} aria-hidden="true" />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="z-50 grid min-w-[220px] gap-1 rounded-[var(--radius-lg)] border border-[var(--border-light)] bg-white p-2 shadow-[var(--shadow-md)]"
          sideOffset={8}
        >
          <button
            className={cn("review-deck-option", selectedDeckId === null && "is-selected")}
            onClick={() => {
              onSelect(null);
              setOpen(false);
            }}
          >
            <span>{t("review_all_decks")}</span>
            <Badge tone="neutral">{decks.length}</Badge>
          </button>
          {decks.map((deck) => (
            <button
              key={deck.id}
              className={cn("review-deck-option", selectedDeckId === deck.id && "is-selected")}
              onClick={() => {
                onSelect(deck.id);
                setOpen(false);
              }}
            >
              <span>{deck.name}</span>
            </button>
          ))}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
