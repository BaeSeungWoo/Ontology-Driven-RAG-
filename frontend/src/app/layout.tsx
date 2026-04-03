import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "../styles/themes/factory-themes.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Ontology-Driven-RAG",
  description: "Ontology-Driven-RAG",
  icons: {
    icon: "/logo3.png",
    shortcut: "/logo3.png",
    apple: "/logo3.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // .env.local examples:
  // NEXT_PUBLIC_FACTORY_THEME=default
  // NEXT_PUBLIC_FACTORY_THEME=fac_YM
  // NEXT_PUBLIC_FACTORY_THEME=fac_PS
  // NEXT_PUBLIC_FACTORY_THEME=fac_SD
  const themeKey = process.env.NEXT_PUBLIC_FACTORY_THEME || "default";
  const themeClassMap: Record<string, string> = {
    default: "theme-factory-default",
    fac_YM: "theme-factory-ym",
    fac_PS: "theme-factory-ps",
    fac_SD: "theme-factory-sd",
  };
  const factoryThemeClass =
    themeClassMap[themeKey] || themeClassMap.default;

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className={`min-h-full flex flex-col ${factoryThemeClass}`}>
        {children}
      </body>
    </html>
  );
}
