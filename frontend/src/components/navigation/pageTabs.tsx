"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLayoutEffect, useRef, useState } from "react";
import styles from "./pageTabs.module.css";

const PAGE_TABS = [
  { href: "/chat", label: "Ontology-RAG Driven CNC assistant" },
  { href: "/cms", label: "AI 데일리 생산 리포트" },
  { href: "/mes", label: "AI 데일리 경영 리포트" },
] as const;

export default function PageTabs() {
  const pathname = usePathname();
  const navRef = useRef<HTMLElement>(null);
  const [hoveredTab, setHoveredTab] = useState<string | null>(null);
  const [focusedTab, setFocusedTab] = useState<string | null>(null);

  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return;

    const links = Array.from(nav.querySelectorAll("a"));
    const target = links.find((link) => link.getAttribute("href") === (hoveredTab ?? focusedTab))
      ?? links.find((link) => link.getAttribute("aria-current") === "page");
    const updateIndicator = () => {
      nav.style.setProperty("--tab-indicator-left", `${target?.offsetLeft ?? 0}px`);
      nav.style.setProperty("--tab-indicator-width", `${target?.offsetWidth ?? 0}px`);
    };

    updateIndicator();
    const observer = new ResizeObserver(updateIndicator);
    observer.observe(nav);
    links.forEach((link) => observer.observe(link));
    return () => observer.disconnect();
  }, [pathname, hoveredTab, focusedTab]);

  return (
    <nav
      ref={navRef}
      className={styles.tabs}
      aria-label="Page navigation tabs"
      onMouseLeave={() => setHoveredTab(null)}
    >
      {PAGE_TABS.map((tab) => {
        const isActive =
          pathname === tab.href || pathname.startsWith(`${tab.href}/`);

        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`${styles.tab} ${isActive ? styles.tabActive : ""}`}
            aria-current={isActive ? "page" : undefined}
            onMouseEnter={() => setHoveredTab(tab.href)}
            onFocus={() => setFocusedTab(tab.href)}
            onBlur={() => setFocusedTab(null)}
          >
            {tab.label}
          </Link>
        );
      })}
      <span className={styles.indicator} data-tab-indicator aria-hidden="true" />
    </nav>
  );
}
