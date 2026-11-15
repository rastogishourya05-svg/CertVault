import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "CertVault — Make room for your next milestone",
  description:
    "Your learning, beautifully collected. A private certificate vault.",
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
