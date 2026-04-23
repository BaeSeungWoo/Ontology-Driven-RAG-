"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./pageTabs.module.css";

const PAGE_TABS = [
  { href: "/chat", label: "Chat" },
  { href: "/checkpoint", label: "CheckPoint" },
  { href: "/dailyReport", label: "DailyReport" },
] as const;

export default function PageTabs() {
  const pathname = usePathname();

  return (
    <nav className={styles.tabs} aria-label="Page navigation tabs">
      {PAGE_TABS.map((tab) => {
        const isActive =
          pathname === tab.href || pathname.startsWith(`${tab.href}/`);

        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`${styles.tab} ${isActive ? styles.tabActive : ""}`}
            aria-current={isActive ? "page" : undefined}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
