"use client";

import { useMemo, useState } from "react";
import type { EquipAlarmRowApi, EquipEffectRowApi, EquipmentMetricsApi, Section06 } from "@/types/checkpoint";
import styles from "../checkpoint.module.css";
import SectionTable, { type TableColumn } from "../sectionTable";
import SectionTabs, { type SectionTabItem } from "../sectionTabs";

type Section06Props = {
  section06Data?: Section06;
  isLoading?: boolean;
  errorMessage?: string;
};

export default function EquipSection({
  section06Data,
  isLoading = false,
  errorMessage = "",
}: Section06Props) {
  const [activePanel, setActivePanel] = useState<"summary" | "alarm" | "effect">("summary");
  const tabItems: SectionTabItem<"summary" | "alarm" | "effect">[] = [
    { key: "summary", label: "6.1 설비요약" },
    { key: "alarm", label: "6.2 설비 알람분석" },
    { key: "effect", label: "6.3 설비 영향분석" },
  ];

  const summaryRows = section06Data?.summary ?? [];
  const alarmRows = section06Data?.alram ?? [];
  const effectRows = section06Data?.effect ?? [];

  const summaryColumns: TableColumn<EquipmentMetricsApi>[] = [
    { header: "전체설비수", render: (row) => row.totalEquipQty, align: "right" },
    { header: "가동설비수", render: (row) => row.runningEquipQty, align: "right" },
    { header: "가동률(%)", render: (row) => row.runningRate, align: "right" },
    { header: "알람설비수", render: (row) => row.alarmEquipQty, align: "right" },
    { header: "알람건수", render: (row) => row.alarmCnt, align: "right" },
    { header: "설비상태", render: (row) => row.status ?? "-", align: "left" },
  ];

  const alarmColumns = useMemo<TableColumn<EquipAlarmRowApi>[]>(
    () => [
      { header: "설비코드", render: (row) => row.equipCode ?? "-", align: "left" },
      { header: "설비명", render: (row) => row.equipName ?? "-", align: "left" },
      { header: "알람코드", render: (row) => row.alramCode ?? "-", align: "left" },
      { header: "알람내용", render: (row) => row.alramMessage ?? "-", align: "left" },
      { header: "조치내용", render: (row) => row.action ?? "-", align: "left" },
    ],
    []
  );

  const effectColumns = useMemo<TableColumn<EquipEffectRowApi>[]>(
    () => [
      { header: "설비코드", render: (row) => row.equipCode ?? "-", align: "left" },
      { header: "설비명", render: (row) => row.equipName ?? "-", align: "left" },
      { header: "영향내용", render: (row) => row.effect ?? "-", align: "left" },
      { header: "영향시간", render: (row) => row.effectTime ?? "-", align: "left" },
      { header: "설비정지시간", render: (row) => row.stopTime ?? "-", align: "left" },
    ],
    []
  );

  return (
    <article className={styles.card}>
      <h2>6. 설비 현황 (Equipment)</h2>

      <div className={styles.sectionFrame}>
        <SectionTabs
          items={tabItems}
          activeKey={activePanel}
          onChange={setActivePanel}
          ariaLabel="설비현황 섹션 선택"
          variant="section"
        />

        {activePanel === "summary" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>6.1 설비요약</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section06Data?.summaryComment ?? "-"}
            </p>
            <SectionTable columns={summaryColumns} rows={summaryRows} rowKey={(_, i) => `equip-summary-${i}`} />
          </div>
        ) : null}

        {activePanel === "alarm" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>6.2 설비 알람분석</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section06Data?.alramComment ?? "-"}
            </p>
            <SectionTable columns={alarmColumns} rows={alarmRows} rowKey={(_, i) => `equip-alarm-${i}`} />
          </div>
        ) : null}

        {activePanel === "effect" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>6.3 설비 영향분석</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section06Data?.effectComment ?? "-"}
            </p>
            <SectionTable columns={effectColumns} rows={effectRows} rowKey={(_, i) => `equip-effect-${i}`} />
          </div>
        ) : null}
      </div>

      {errorMessage ? <p className={styles.metricsDebugError}>{errorMessage}</p> : null}
    </article>
  );
}
