"use client";

import { useEffect, useState } from "react";
import PageTabs from "@/components/navigation/pageTabs";
import ThemeSwitcher, { type ThemeKey } from "@/components/chat/themeSwitcher/themeSwitcher";
import { getCheckPointSections } from "@/services/checkpointApi";
import type { CheckPointSectionsResponse , CheckPointSectionsRequest } from "@/types/checkpoint";
import styles from "./checkpoint.module.css";
import SummarySection from "./01_Summary/summary";
import ProductionSection from "./02_Production/production";
import ShippingSection from "./03_Shipping/shipping";
import DeliverySection from "./04_Delivery/delivery";
import QualitySection from "./05_Quality/quality";
import EquipSection from "./06_Equip/equip";
import SectionTabs, { type SectionTabItem } from "./sectionTabs";

const REPORT_SECTIONS_REQUEST: CheckPointSectionsRequest = {
  date: "2026-03-06",
  // date: "2025-08-20",
  reportId: "OBI",
  locale: "ko_KR",
  config: "ollama_config"
};

export default function CheckPoint() {
  const themeKey =
    (process.env.NEXT_PUBLIC_FACTORY_THEME as ThemeKey) || "default";
  const [data, setData] = useState<CheckPointSectionsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStartedAt, setLoadingStartedAt] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [errorMessage, setErrorMessage] = useState("");
  const [activeTopTab, setActiveTopTab] = useState<
    "summary" | "production" | "shipping" | "delivery" | "quality" | "equip"
  >("summary");
  const topTabItems: SectionTabItem<
    "summary" | "production" | "shipping" | "delivery" | "quality" | "equip"
  >[] = [
    { key: "summary", label: "1. 경영층 요약" },
    { key: "production", label: "2. 생산현황" },
    { key: "shipping", label: "3. 출하현황" },
    { key: "delivery", label: "4. 납기현황" },
    { key: "quality", label: "5. 품질현황" },
    { key: "equip", label: "6. 설비현황" },
  ];

  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      setIsLoading(true);
      setLoadingStartedAt(Date.now());
      setElapsedMs(0);
      setErrorMessage("");

      try {
        const result = await getCheckPointSections(REPORT_SECTIONS_REQUEST);
        if (!isMounted) return;
        
        setData(result);
      } catch (error) {
        if (!isMounted) return;
        const message =
          error instanceof Error
            ? error.message
            : "리포트 섹션 데이터를 불러오는 중 오류가 발생했습니다.";
        setErrorMessage(message);
      } finally {
        if (isMounted) {
          setIsLoading(false);
          setLoadingStartedAt(null);
        }
      }
    };

    load();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!isLoading || loadingStartedAt === null) return;
    const timerId = window.setInterval(() => {
      setElapsedMs(Date.now() - loadingStartedAt);
    }, 200);
    return () => {
      window.clearInterval(timerId);
    };
  }, [isLoading, loadingStartedAt]);

  function formatElapsed(ms: number) {
    const totalSeconds = Math.floor(ms / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  return (
    <div className="tw-chat-page">
      <div className="tw-chat-toolbar">
        <div className={styles.reportToolbarLeft}>
          <h1 className="tw-chat-title">Ontology-Driven-RAG</h1>
          <PageTabs />
        </div>
        <ThemeSwitcher initialTheme={themeKey} />
      </div>

      <main className={styles.reportBody}>
        <section className={styles.reportStack}>
          {isLoading ? (
            <div className={styles.loadingNotice} role="status" aria-live="polite">
              <span className={styles.loadingSpinner} aria-hidden="true" />
              <div className={styles.loadingTextWrap}>
                <strong className={styles.loadingTitle}>데이터 로딩 중</strong>
                <span className={styles.loadingElapsed}>
                  경과시간 {formatElapsed(elapsedMs)}
                </span>
              </div>
            </div>
          ) : null}

          <SectionTabs
            items={topTabItems}
            activeKey={activeTopTab}
            onChange={setActiveTopTab}
            ariaLabel="체크포인트 상위 섹션"
            variant="top"
          />

          <div className={styles.topTabPanel}>
            {activeTopTab === "summary" ? (
              <SummarySection
                section01Data={data?.Section_01}
                isLoading={isLoading}
                errorMessage={errorMessage}
              />
            ) : null}

            {activeTopTab === "production" ? (
              <ProductionSection
                section02Data={data?.Section_02}
                isLoading={isLoading}
                errorMessage={errorMessage}
              />
            ) : null}

            {activeTopTab === "shipping" ? (
              <ShippingSection
                section03Data={data?.Section_03}
                isLoading={isLoading}
                errorMessage={errorMessage}
              />
            ) : null}

            {activeTopTab === "delivery" ? (
              <DeliverySection
                section04Data={data?.Section_04}
                isLoading={isLoading}
                errorMessage={errorMessage}
              />
            ) : null}

            {activeTopTab === "quality" ? (
              <QualitySection
                section05Data={data?.Section_05}
                isLoading={isLoading}
                errorMessage={errorMessage}
              />
            ) : null}

            {activeTopTab === "equip" ? (
              <EquipSection
                section06Data={data?.Section_06}
                isLoading={isLoading}
                errorMessage={errorMessage}
              />
            ) : null}
          </div>
        </section>
      </main>
    </div>
  );
}
