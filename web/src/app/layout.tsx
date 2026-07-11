import type { Metadata, Viewport } from "next";
import Header from "@/components/Header";
import InstallPromptCapture from "@/components/InstallPromptCapture";
import OfflineBanner from "@/components/OfflineBanner";
import SwRegister from "@/components/SwRegister";
import "./globals.css";

/* Next does not basePath-prefix metadata asset URLs, so the GitHub Pages
   build (/place) has to do it by hand. */
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title: "Place",
  description: "What's good right now, near you.",
  manifest: `${BASE_PATH}/manifest.webmanifest`,
  // iOS ignores manifest icons — without the apple-touch-icon link the
  // Home-Screen install (the iOS push prerequisite, UI-DRAFT-BRIEF §8)
  // falls back to a page screenshot.
  icons: {
    icon: `${BASE_PATH}/icon.svg`,
    apple: `${BASE_PATH}/apple-touch-icon.png`,
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#29583F",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <Header />
        <main className="shell">
          {/* §9 state (a): the offline shell is designed once — the banner
              mounts here so every route degrades identically. */}
          <OfflineBanner />
          {children}
        </main>
        <SwRegister />
        <InstallPromptCapture />
      </body>
    </html>
  );
}
