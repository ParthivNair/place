import Link from "next/link";
import styles from "./Header.module.css";

/* Quiet top chrome — no tab bar (UI-DRAFT-BRIEF decision 1): the feed is
   home; saves and account live behind quiet top-right targets. The account
   glyph routes to /saves until a settings surface exists. */
export default function Header() {
  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link href="/" className={styles.wordmark}>
          Place
        </Link>
        <nav className={styles.actions} aria-label="Saves and account">
          <Link href="/saves" className={styles.iconLink} aria-label="Saved places">
            <span className={styles.heart} aria-hidden="true">
              ♡
            </span>
          </Link>
          <Link href="/saves" className={styles.iconLink} aria-label="Account">
            <svg
              className={styles.accountGlyph}
              width="20"
              height="20"
              viewBox="0 0 20 20"
              aria-hidden="true"
            >
              <circle
                cx="10"
                cy="6.75"
                r="3.25"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              />
              <path
                d="M3.75 16.5c1.25-2.7 3.55-4 6.25-4s5 1.3 6.25 4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </Link>
        </nav>
      </div>
    </header>
  );
}
