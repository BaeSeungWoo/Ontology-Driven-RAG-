"use client";

import styles from "./checkpoint.module.css";

export type SectionTabItem<T extends string> = {
  key: T;
  label: string;
};

type SectionTabsProps<T extends string> = {
  items: SectionTabItem<T>[];
  activeKey: T;
  onChange: (key: T) => void;
  ariaLabel: string;
  variant?: "top" | "section";
};

// Shared tab bar for checkpoint screens.
// - top: top-level tabs (e.g. section 1/2)
// - section: in-card subsection tabs
export default function SectionTabs<T extends string>({
  items,
  activeKey,
  onChange,
  ariaLabel,
  variant = "section",
}: SectionTabsProps<T>) {
  const barClass = variant === "top" ? styles.topTabBar : styles.sectionTabs;
  const tabClass = variant === "top" ? styles.topTab : styles.sectionTab;
  const activeClass = variant === "top" ? styles.topTabActive : styles.sectionTabActive;

  return (
    <div className={barClass} role="tablist" aria-label={ariaLabel}>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          role="tab"
          aria-selected={activeKey === item.key}
          className={`${tabClass} ${activeKey === item.key ? activeClass : ""}`}
          onClick={() => onChange(item.key)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
