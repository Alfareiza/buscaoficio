"use client";

import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";
import Image from "next/image";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Check, ChevronsUpDown, X } from "lucide-react";

import { cn } from "@/lib/utils";

export type MultiSelectOption = {
  value: string;
  label: string;
  icon?: string;
};

type MultiSelectProps = {
  value: string[];
  onValueChange: (value: string[]) => void;
  options: MultiSelectOption[];
  placeholder?: string;
  searchLabel: string;
  emptyText: string;
  listLabel: string;
};

function fuzzyMatch(haystack: string, query: string) {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return true;
  const source = haystack.toLocaleLowerCase();
  let queryIndex = 0;
  for (const character of source) {
    if (character === needle[queryIndex]) queryIndex += 1;
    if (queryIndex === needle.length) return true;
  }
  return false;
}

export function MultiSelect({
  value,
  onValueChange,
  options,
  placeholder,
  searchLabel,
  emptyText,
  listLabel,
}: MultiSelectProps) {
  const reduce = useReducedMotion() ?? false;
  const listId = useId();
  const inputId = useId();
  const triggerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeValue, setActiveValue] = useState<string | null>(null);
  const [coords, setCoords] = useState<{
    top: number;
    left: number;
    width: number;
  } | null>(null);

  const optionByValue = useMemo(
    () => new Map(options.map((option) => [option.value, option])),
    [options],
  );
  const visibleOptions = useMemo(
    () =>
      options.filter((option) =>
        fuzzyMatch(`${option.label} ${option.value}`, query),
      ),
    [options, query],
  );

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;
    const update = () => {
      const rect = triggerRef.current?.getBoundingClientRect();
      if (!rect) return;
      setCoords({ top: rect.bottom + 6, left: rect.left, width: rect.width });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [open, value.length]);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() =>
      inputRef.current?.focus({ preventScroll: true }),
    );
    return () => cancelAnimationFrame(frame);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (
        triggerRef.current?.contains(target) ||
        contentRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
      setQuery("");
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (!open) {
      setActiveValue(null);
      return;
    }
    if (
      activeValue &&
      visibleOptions.some((option) => option.value === activeValue)
    ) {
      return;
    }
    setActiveValue(visibleOptions[0]?.value ?? null);
  }, [activeValue, open, visibleOptions]);

  function toggle(next: string) {
    onValueChange(
      value.includes(next)
        ? value.filter((item) => item !== next)
        : [...value, next],
    );
    setQuery("");
    requestAnimationFrame(() =>
      inputRef.current?.focus({ preventScroll: true }),
    );
  }

  function remove(next: string) {
    onValueChange(value.filter((item) => item !== next));
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Backspace" && !query && value.length) {
      event.preventDefault();
      remove(value[value.length - 1]);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const index = visibleOptions.findIndex(
        (option) => option.value === activeValue,
      );
      if (visibleOptions.length === 0) return;
      const delta = event.key === "ArrowDown" ? 1 : -1;
      const nextIndex =
        index === -1
          ? 0
          : (index + delta + visibleOptions.length) % visibleOptions.length;
      setActiveValue(visibleOptions[nextIndex].value);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      if (activeValue) toggle(activeValue);
      return;
    }
    if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
      setQuery("");
    }
  }

  const showPlaceholder = Boolean(placeholder) && value.length === 0 && !open;

  return (
    <div className="relative w-full">
      <div
        ref={triggerRef}
        data-state={open ? "open" : "closed"}
        onPointerDown={(event) => {
          const target = event.target as HTMLElement;
          if (
            target === inputRef.current ||
            target.closest("[data-multi-select-remove]")
          ) {
            return;
          }
          event.preventDefault();
          inputRef.current?.focus({ preventScroll: true });
          setOpen(true);
        }}
        className={cn(
          "relative z-20 flex min-h-11 w-full cursor-text items-center gap-2 rounded-xl border border-gray-200 bg-white px-2.5 py-1.5 text-sm text-azul transition-colors",
          "hover:border-gray-400 focus-within:border-naranja focus-within:ring-2 focus-within:ring-naranja/30",
          "dark:border-gray-600 dark:bg-gray-900 dark:text-white",
        )}
      >
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
          {showPlaceholder ? (
            <span className="px-1 text-sm text-gray-400">{placeholder}</span>
          ) : null}
          <AnimatePresence initial={false}>
            {value.map((item) => {
              const option = optionByValue.get(item);
              const label = option?.label ?? item;
              return (
                <motion.span
                  layout={reduce ? false : "position"}
                  key={item}
                  initial={
                    reduce ? false : { opacity: 0, y: 6, scale: 0.92 }
                  }
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={
                    reduce
                      ? { opacity: 0 }
                      : { opacity: 0, scale: 0.92 }
                  }
                  transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                  className="inline-flex h-7 max-w-full items-center gap-1 rounded-lg bg-gray-100 px-2 text-xs font-medium text-azul dark:bg-gray-800 dark:text-white"
                >
                  {option?.icon ? (
                    <Image
                      src={option.icon}
                      alt=""
                      width={16}
                      height={16}
                      className="size-4 shrink-0 object-contain"
                    />
                  ) : null}
                  <span className="truncate">{label}</span>
                  <button
                    type="button"
                    data-multi-select-remove=""
                    aria-label={`Quitar ${label}`}
                    onPointerDown={(event) => event.stopPropagation()}
                    onClick={(event) => {
                      event.stopPropagation();
                      remove(item);
                      inputRef.current?.focus({ preventScroll: true });
                    }}
                    className="-mr-1 grid size-5 shrink-0 place-items-center rounded-md text-gray-500 outline-none transition-colors hover:bg-black/5 hover:text-azul focus-visible:ring-2 focus-visible:ring-naranja/50 dark:hover:bg-white/10 dark:hover:text-white"
                  >
                    <X aria-hidden className="size-3" strokeWidth={2} />
                  </button>
                </motion.span>
              );
            })}
          </AnimatePresence>
          <input
            ref={inputRef}
            id={inputId}
            role="combobox"
            aria-label={searchLabel}
            aria-autocomplete="list"
            aria-expanded={open}
            aria-controls={listId}
            aria-activedescendant={open && activeValue ? activeValue : undefined}
            autoComplete="off"
            value={query}
            placeholder={value.length ? "" : "Buscar…"}
            onFocus={() => setOpen(true)}
            onClick={() => setOpen(true)}
            onChange={(event) => {
              setOpen(true);
              setQuery(event.target.value);
            }}
            onKeyDown={handleKeyDown}
            className="h-7 min-w-12 flex-1 bg-transparent text-sm text-azul outline-none placeholder:text-gray-400 disabled:cursor-not-allowed dark:text-white"
          />
        </div>
        <ChevronsUpDown
          aria-hidden
          className="size-4 shrink-0 text-gray-400"
          strokeWidth={1.75}
        />
      </div>

      {open && coords
        ? createPortal(
            <div
              ref={contentRef}
              className="fixed z-[80] overflow-hidden rounded-xl border border-gray-200 bg-white text-azul shadow-[0_12px_40px_rgba(26,60,110,0.12)] dark:border-gray-700 dark:bg-gray-900 dark:text-white"
              style={{
                top: coords.top,
                left: coords.left,
                width: coords.width,
              }}
            >
              <div
                id={listId}
                role="listbox"
                aria-label={listLabel}
                aria-multiselectable="true"
                className="max-h-64 overflow-y-auto p-1.5"
              >
                {visibleOptions.length === 0 ? (
                  <div
                    role="status"
                    className="px-3 py-8 text-center text-sm text-gray-500"
                  >
                    {emptyText}
                  </div>
                ) : (
                  visibleOptions.map((option) => {
                    const selected = value.includes(option.value);
                    const active = activeValue === option.value;
                    return (
                      <button
                        key={option.value}
                        id={option.value}
                        type="button"
                        role="option"
                        aria-selected={selected}
                        tabIndex={-1}
                        data-active={active || undefined}
                        onPointerMove={() => setActiveValue(option.value)}
                        onPointerDown={(event) => event.preventDefault()}
                        onClick={() => toggle(option.value)}
                        className={cn(
                          "relative flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-sm outline-none transition-colors",
                          active || selected
                            ? "bg-gray-100 text-azul dark:bg-gray-800 dark:text-white"
                            : "text-gray-600 dark:text-gray-300",
                        )}
                      >
                        {option.icon ? (
                          <Image
                            src={option.icon}
                            alt=""
                            width={28}
                            height={28}
                            className="size-7 shrink-0 object-contain"
                          />
                        ) : null}
                        <span className="min-w-0 flex-1">{option.label}</span>
                        <span
                          aria-hidden
                          className={cn(
                            "grid size-5 place-items-center text-azul transition-opacity dark:text-white",
                            selected ? "opacity-100" : "opacity-0",
                          )}
                        >
                          <Check className="size-4" strokeWidth={2} />
                        </span>
                      </button>
                    );
                  })
                )}
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
