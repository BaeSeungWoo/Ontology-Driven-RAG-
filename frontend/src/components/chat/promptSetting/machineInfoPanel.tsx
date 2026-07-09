"use client";

import type { MachineInfo } from "@/types/prompt";
import styles from "./promptSetting.module.css";

type MachineInfoPanelProps = {
  machineCode: string | null;
  machineInfo: MachineInfo | null;
  isMainServer: boolean;
};

export default function MachineInfoPanel({
  machineCode,
  machineInfo,
  isMainServer,
}: MachineInfoPanelProps) {
  const machineName = machineInfo?.machine_name ?? (isMainServer ? "전체 장비" : "장비 미확인");
  const machineCodeText = machineCode ?? "-";
  const machineSpec = machineInfo
    ? `${machineInfo.machine_maker} / ${machineInfo.machine_ver} / ${machineInfo.machine_controller}`
    : "-";
  const documents = machineInfo?.document ?? [];

  return (
    <section className={styles.machineInfoBox} aria-label="장비 정보">
      <p className={styles.machineInfoHeading}>장비 정보</p>
      <dl className={styles.machineInfoList}>
        <div className={styles.machineInfoRow}>
          <dt>장비명</dt>
          <dd>{machineName}</dd>
        </div>
        <div className={styles.machineInfoRow}>
          <dt>장비코드</dt>
          <dd>{machineCodeText}</dd>
        </div>
        <div className={styles.machineInfoRow}>
          <dt>제조사/버전/컨트롤러</dt>
          <dd>{machineSpec}</dd>
        </div>
        <div className={styles.machineInfoRow}>
          <dt>참조문서</dt>
          <dd>
            {documents.length > 0 ? (
              <ul className={styles.machineDocumentList}>
                {documents.map((documentName) => (
                  <li key={documentName}>{documentName}</li>
                ))}
              </ul>
            ) : (
              "-"
            )}
          </dd>
        </div>
      </dl>
    </section>
  );
}
