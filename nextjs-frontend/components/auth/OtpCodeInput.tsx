"use client";

import { useRef, type ClipboardEvent, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";

const OTP_LENGTH = 6;

interface OtpCodeInputProps {
  value: string;
  onChange: (value: string) => void;
  onComplete: (value: string) => void;
  disabled?: boolean;
  invalid?: boolean;
}

export function OtpCodeInput({
  value,
  onChange,
  onComplete,
  disabled = false,
  invalid = false,
}: OtpCodeInputProps) {
  const inputsRef = useRef<Array<HTMLInputElement | null>>([]);

  function focusAt(index: number) {
    const next = Math.max(0, Math.min(OTP_LENGTH - 1, index));
    inputsRef.current[next]?.focus();
    inputsRef.current[next]?.select();
  }

  function apply(next: string) {
    const sanitized = next.replace(/\D/g, "").slice(0, OTP_LENGTH);
    onChange(sanitized);
    if (sanitized.length === OTP_LENGTH) {
      onComplete(sanitized);
    }
  }

  function handleChange(index: number, raw: string) {
    if (disabled) return;
    const incoming = raw.replace(/\D/g, "");

    if (incoming.length === 0) {
      apply(value.slice(0, index) + value.slice(index + 1));
      return;
    }

    if (incoming.length > 1) {
      const merged = (value.slice(0, index) + incoming).slice(0, OTP_LENGTH);
      apply(merged);
      if (merged.length < OTP_LENGTH) {
        focusAt(merged.length);
      }
      return;
    }

    const merged = (
      value.slice(0, index) +
      incoming +
      value.slice(index + 1)
    ).slice(0, OTP_LENGTH);
    apply(merged);
    if (merged.length < OTP_LENGTH) {
      focusAt(index + 1);
    }
  }

  function handleKeyDown(
    index: number,
    event: KeyboardEvent<HTMLInputElement>,
  ) {
    if (disabled) return;

    if (event.key === "Backspace") {
      event.preventDefault();
      if (value[index]) {
        apply(value.slice(0, index));
      } else if (index > 0) {
        apply(value.slice(0, index - 1));
        focusAt(index - 1);
      }
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusAt(index - 1);
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusAt(index + 1);
    }
  }

  function handlePaste(index: number, event: ClipboardEvent<HTMLInputElement>) {
    event.preventDefault();
    if (disabled) return;
    const pasted = event.clipboardData.getData("text").replace(/\D/g, "");
    if (!pasted) return;
    const merged = (value.slice(0, index) + pasted).slice(0, OTP_LENGTH);
    apply(merged);
    if (merged.length < OTP_LENGTH) {
      focusAt(merged.length);
    }
  }

  return (
    <div
      role="group"
      aria-label="Código de verificación"
      className="flex w-full justify-center gap-1.5 sm:gap-2.5"
    >
      {Array.from({ length: OTP_LENGTH }, (_, index) => {
        const digit = value[index] ?? "";
        const filled = digit !== "";
        return (
          <input
            key={index}
            ref={(el) => {
              inputsRef.current[index] = el;
            }}
            type="text"
            inputMode="numeric"
            autoComplete={index === 0 ? "one-time-code" : "off"}
            autoFocus={index === 0}
            maxLength={index === 0 ? OTP_LENGTH : 1}
            pattern="\d*"
            aria-label={`Dígito ${index + 1} de ${OTP_LENGTH}`}
            disabled={disabled}
            value={digit}
            onChange={(event) => handleChange(index, event.target.value)}
            onKeyDown={(event) => handleKeyDown(index, event)}
            onPaste={(event) => handlePaste(index, event)}
            onFocus={(event) => event.target.select()}
            className={cn(
              "h-14 min-w-0 flex-1 max-w-12 rounded-lg border text-center text-xl font-semibold text-azul caret-azul transition-[background-color,border-color,box-shadow] duration-150 sm:h-[4.5rem]",
              "focus:outline-none",
              filled
                ? "border-gray-200 bg-gray-100 dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                : "border-gray-200 bg-white dark:border-gray-700 dark:bg-transparent dark:text-white",
              "focus:border-gray-400 focus:shadow-[0_1px_4px_rgba(0,0,0,0.12)] dark:focus:border-gray-500",
              invalid && "border-red-300 focus:border-red-400",
              disabled && "cursor-not-allowed opacity-60",
            )}
          />
        );
      })}
    </div>
  );
}
