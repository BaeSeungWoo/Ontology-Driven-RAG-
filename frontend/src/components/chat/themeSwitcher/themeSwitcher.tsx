"use client";

import { useState } from "react";
import styles from "./themeSwitcher.module.css";

export type ThemeKey = "default" | "fac_YM" | "fac_PS" | "fac_YG";

const themeClassMap: Record<ThemeKey, string> = {
  default: "theme-factory-default",
  fac_YM: "theme-factory-ym",
  fac_PS: "theme-factory-ps",
  fac_YG: "theme-factory-yg",
};

const themeLabelMap: Record<ThemeKey, string> = {
  default: "디폴트",
  fac_YM: "연암",
  fac_PS: "풍산",
  fac_YG: "율곡",
};

const allThemeClasses = Object.values(themeClassMap);

type ThemeSwitcherProps = {
  initialTheme: ThemeKey;
};

export default function ThemeSwitcher({ initialTheme }: ThemeSwitcherProps) {
  const [activeTheme, setActiveTheme] = useState<ThemeKey>(initialTheme);

  const applyTheme = (nextTheme: ThemeKey) => {
    document.body.classList.remove(...allThemeClasses);
    document.body.classList.add(themeClassMap[nextTheme]);
    setActiveTheme(nextTheme);
  };

  return (
    <div className={styles.themeSwitcher}>
      <span className={styles.label}>테마 적용 테스트</span>
      <div className={styles.buttons}>
        {(Object.keys(themeClassMap) as ThemeKey[]).map((theme) => (
          <button
            key={theme}
            type="button"
            className={`${styles.button} ${
              activeTheme === theme ? styles.buttonActive : ""
            }`}
            onClick={() => applyTheme(theme)}
          >
            {themeLabelMap[theme]}
          </button>
        ))}
      </div>
    </div>
  );
}
