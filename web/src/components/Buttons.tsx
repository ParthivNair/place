"use client";

import type { MouseEventHandler, ReactNode } from "react";
import Link from "next/link";
import styles from "./Buttons.module.css";

export interface PrimaryButtonProps {
  children: ReactNode;
  onClick?: MouseEventHandler<HTMLButtonElement>;
  disabled?: boolean;
  type?: "button" | "submit" | "reset";
}

// "I'm going" — the only conversion the card wants (docs/02 §3).
export function PrimaryButton({
  children,
  onClick,
  disabled,
  type = "button",
}: PrimaryButtonProps) {
  return (
    <button
      type={type}
      className={`${styles.btn} ${styles.primary}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export interface TertiaryButtonProps {
  children: ReactNode;
  onClick?: MouseEventHandler<HTMLElement>;
  href?: string;
}

// Canonical tertiary: quiet text button, ink-soft, no border, trailing →
// supplied by the caller (glyph canon: → is tertiary/link-out only).
export function TertiaryButton({ children, onClick, href }: TertiaryButtonProps) {
  const className = `${styles.btn} ${styles.tertiary}`;
  if (href) {
    return (
      <Link href={href} className={className} onClick={onClick}>
        {children}
      </Link>
    );
  }
  return (
    <button type="button" className={className} onClick={onClick}>
      {children}
    </button>
  );
}

export interface SaveHeartProps {
  saved: boolean;
  onToggle?: MouseEventHandler<HTMLButtonElement>;
  label?: string;
}

// ♡/♥ is reserved for saves (glyph canon); hollow = unsaved.
export function SaveHeart({ saved, onToggle, label = "Save" }: SaveHeartProps) {
  return (
    <button
      type="button"
      className={styles.saveHeart}
      aria-pressed={saved}
      aria-label={label}
      onClick={onToggle}
    >
      <span
        className={saved ? `${styles.heart} ${styles.heartSaved}` : styles.heart}
        aria-hidden="true"
      >
        {saved ? "♥" : "♡"}
      </span>
    </button>
  );
}
