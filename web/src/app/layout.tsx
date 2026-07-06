import type { Metadata, Viewport } from "next";
import Header from "@/components/Header";
import InstallPromptCapture from "@/components/InstallPromptCapture";
import OfflineBanner from "@/components/OfflineBanner";
import SwRegister from "@/components/SwRegister";
import "./globals.css";

export const metadata: Metadata = {
  title: "Place",
  description: "What's good right now, near you.",
  manifest: "/manifest.webmanifest",
  // iOS ignores manifest icons — without the apple-touch-icon link the
  // Home-Screen install (the iOS push prerequisite, UI-DRAFT-BRIEF §8)
  // falls back to a page screenshot.
  icons: {
    icon: "/icon.svg",
    apple: "/apple-touch-icon.png",
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
