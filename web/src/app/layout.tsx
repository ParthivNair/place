import type { Metadata, Viewport } from "next";
import Header from "@/components/Header";
import SwRegister from "@/components/SwRegister";
import "./globals.css";

export const metadata: Metadata = {
  title: "Place",
  description: "What's good right now, near you.",
  manifest: "/manifest.webmanifest",
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
        <main className="shell">{children}</main>
        <SwRegister />
      </body>
    </html>
  );
}
