import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trading Intelligence Platform",
  description:
    "AI-powered trading analyst & research platform for Indian markets (NSE / BSE / MCX). Decision support only.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
