import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Relations · Relationship Intelligence",
  description: "Discover people. Build meaningful connections.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
