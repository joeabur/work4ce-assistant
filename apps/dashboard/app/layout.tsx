import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Work4ce Assistant · Analyst workbench",
  description:
    "Evidence-led investigations and human-governed review in a synthetic security workspace.",
  robots: { index: false, follow: false },
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
