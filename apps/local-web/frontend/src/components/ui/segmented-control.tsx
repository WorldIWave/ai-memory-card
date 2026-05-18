/**
 * Input: options?????onChange  |  Output: ??????????????
 * Output: ??????????????????
 * Role: ???????????????????????
 * Use: ???????????????? SelectField ????? segmented control
 */
import { useRef } from "react";
import type { CSSProperties, KeyboardEvent, ReactNode } from "react";
import { cn } from "../../lib/utils";

export interface SegmentedControlOption<T extends string | number> {
  value: T;
  label: ReactNode;
  disabled?: boolean;
}

export interface SegmentedControlProps<T extends string | number> {
  label: string;
  value: T;
  options: readonly SegmentedControlOption<T>[];
  onChange: (value: T) => void;
  className?: string;
}

export function SegmentedControl<T extends string | number>({
  label,
  value,
  options,
  onChange,
  className,
}: SegmentedControlProps<T>) {
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const activeIndex = options.findIndex((option) => option.value === value);
  const tabStopIndex = activeIndex >= 0 ? activeIndex : options.findIndex((option) => !option.disabled);
  const fallbackTabStopIndex = tabStopIndex >= 0 ? tabStopIndex : 0;
  const controlStyle = {
    "--segment-count": String(Math.max(options.length, 1)),
    "--active-index": String(Math.max(activeIndex, 0)),
    "--active-offset": `${Math.max(activeIndex, 0) * 100}%`,
  } as CSSProperties;

  const focusOption = (index: number) => {
    buttonRefs.current[index]?.focus();
  };

  const moveToIndex = (index: number) => {
    const option = options[index];
    if (!option || option.disabled) {
      return;
    }

    onChange(option.value);
    focusOption(index);
  };

  const getNextEnabledIndex = (startIndex: number, direction: 1 | -1) => {
    if (!options.length) {
      return -1;
    }

    for (let offset = 1; offset <= options.length; offset += 1) {
      const index = (startIndex + direction * offset + options.length) % options.length;
      if (!options[index]?.disabled) {
        return index;
      }
    }

    return -1;
  };

  const getEdgeEnabledIndex = (edge: "first" | "last") => {
    const ordered = edge === "first" ? options : [...options].reverse();
    const offset = edge === "first" ? 0 : options.length - 1;

    for (const [index, option] of ordered.entries()) {
      if (!option.disabled) {
        return edge === "first" ? index : offset - index;
      }
    }

    return -1;
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex = -1;

    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        nextIndex = getNextEnabledIndex(index, 1);
        break;
      case "ArrowLeft":
      case "ArrowUp":
        nextIndex = getNextEnabledIndex(index, -1);
        break;
      case "Home":
        nextIndex = getEdgeEnabledIndex("first");
        break;
      case "End":
        nextIndex = getEdgeEnabledIndex("last");
        break;
      default:
        return;
    }

    if (nextIndex >= 0) {
      event.preventDefault();
      moveToIndex(nextIndex);
    }
  };

  return (
    <div
      role="radiogroup"
      aria-label={label}
      style={controlStyle}
      className={cn("segmented-control inline-flex items-stretch gap-1", className)}
    >
      {options.map((option, index) => {
        const active = option.value === value;

        return (
          <button
            key={String(option.value)}
            ref={(element) => {
              buttonRefs.current[index] = element;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={option.disabled}
            tabIndex={index === fallbackTabStopIndex ? 0 : -1}
            onClick={() => {
              if (!option.disabled) {
                onChange(option.value);
              }
            }}
            onKeyDown={(event) => handleKeyDown(event, index)}
            className={cn(
              "segmented-control-option",
              "rounded-[var(--radius-md)] px-3 py-1.5 text-sm font-medium",
              "disabled:cursor-not-allowed disabled:opacity-60",
              active
                ? "is-active text-white"
                : "bg-transparent text-[var(--text-muted)]",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
