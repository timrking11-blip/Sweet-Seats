import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sweet Seats — New York, before everyone else",
  description: "A provenance-first concert discovery experience for New York City.",
  applicationName: "Sweet Seats",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: "#100c19",
  colorScheme: "dark",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
