import type { MesViewRow } from "@/services/mesApi";
import styles from "../../mes.module.css";
import { formatNumber, toNumber } from "../reportUtils";

/* ===================================================== */

type SevenDayForecastProps = {
  deliveryDelayRows: MesViewRow[];
  workDepletionRows: MesViewRow[];
  productionTrendRows: MesViewRow[];
  machineOperationRateWeeklyRows: MesViewRow[];
  isLoading: boolean;
  errorMessage: string;
};

/* ===================================================== */

function formatDecimal(value: unknown, maximumFractionDigits: number): string {
  return formatNumber(value, maximumFractionDigits);
}

function getDate(value: unknown): Date | null {
  const dateKey = String(value ?? "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateKey)) return null;
  const date = new Date(`${dateKey}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function clampRate(value: number): number {
  return Math.min(100, Math.max(0, value));
}

function getProductionForecast(rows: MesViewRow[]): { total: number; dailyAverage: number } | null {
  const observations = rows
    .map((row) => ({ date: getDate(row.RESULT_DATE), count: toNumber(row.RESULT_COUNT) }))
    .filter((row): row is { date: Date; count: number } => row.date !== null)
    .sort((left, right) => left.date.getTime() - right.date.getTime())
    .slice(-14);
  if (observations.length === 0) return null;

  const fallbackAverage = observations.reduce((sum, row) => sum + row.count, 0) / observations.length;
  const latestDate = observations.at(-1)!.date;
  let total = 0;

  for (let offset = 1; offset <= 7; offset += 1) {
    const forecastDate = new Date(latestDate);
    forecastDate.setDate(latestDate.getDate() + offset);
    const matchingCounts = observations
      .filter((row) => row.date.getDay() === forecastDate.getDay())
      .map((row) => row.count);
    total += matchingCounts.length > 0
      ? matchingCounts.reduce((sum, count) => sum + count, 0) / matchingCounts.length
      : fallbackAverage;
  }

  return { total, dailyAverage: total / 7 };
}

function getEquipmentForecast(rows: MesViewRow[]): {
  lowCount: number;
  averageRate: number;
  minimumName: string;
  minimumRate: number;
} | null {
  const machines = new Map<string, { name: string; observations: { date: Date; rate: number }[] }>();

  rows.forEach((row) => {
    const date = getDate(row.BASE_DATE);
    if (!date || date.getDay() === 0 || date.getDay() === 6) return;
    const key = String(row.MACHINE_CODE ?? row.MACHINE_NAME ?? "").trim();
    if (!key) return;
    const machine = machines.get(key) ?? {
      name: String(row.MACHINE_NAME ?? "장비명 미등록"),
      observations: [],
    };
    machine.observations.push({ date, rate: toNumber(row.OPERATION_RATE) });
    machines.set(key, machine);
  });

  const forecasts = [...machines.values()].map((machine) => {
    const observations = machine.observations
      .sort((left, right) => left.date.getTime() - right.date.getTime())
      .slice(-5);
    const weightedRate = observations.reduce(
      (sum, observation, index) => sum + clampRate(observation.rate) * (index + 1),
      0,
    );
    const weightTotal = observations.reduce((sum, _, index) => sum + index + 1, 0);
    return {
      name: machine.name,
      rate: weightedRate / weightTotal,
    };
  });
  if (forecasts.length === 0) return null;

  const minimum = forecasts.reduce((lowest, forecast) =>
    forecast.rate < lowest.rate ? forecast : lowest,
  );
  return {
    lowCount: forecasts.filter((forecast) => forecast.rate < 30).length,
    averageRate: forecasts.reduce((sum, forecast) => sum + forecast.rate, 0) / forecasts.length,
    minimumName: minimum.name,
    minimumRate: minimum.rate,
  };
}

function getDepletionMessage(row: MesViewRow | undefined): string {
  if (!row) return "작업 소진 전망 데이터 없음";

  const status = String(row.DEPLETION_STATUS ?? "");
  const newWorkRate = formatDecimal(row.DAILY_AVERAGE_NEW_WORK_COUNT, 2);

  if (status === "NO_COMPLETION") return "최근 4주 완료 실적 없어 계산 불가";
  if (status === "NOT_DEPLETING") return `신규 ${newWorkRate}건/일 · 현재 유입 유지 시 소진 없음`;
  return `신규 ${newWorkRate}건/일 · 순소진 ${formatDecimal(row.NET_DEPLETION_DAYS, 1)}일`;
}

/* ===================================================== */

export default function SevenDayForecast({
  deliveryDelayRows,
  workDepletionRows,
  productionTrendRows,
  machineOperationRateWeeklyRows,
  isLoading,
  errorMessage,
}: SevenDayForecastProps) {
  const row = deliveryDelayRows[0];
  const depletionRow = workDepletionRows[0];
  const hasGrossDepletionDays = depletionRow?.GROSS_DEPLETION_DAYS != null;
  const productionForecast = getProductionForecast(productionTrendRows);
  const equipmentForecast = getEquipmentForecast(machineOperationRateWeeklyRows);

  return (
    <section
      className={`${styles.reportSection} ${styles.reportSectionWide} ${styles.sevenDayForecastSection}`}
      aria-label="향후 7일 전망"
    >
      <header className={styles.sevenDayForecastHeader}>
        <h3>향후 7일 전망</h3>
        <span>최근 실측 데이터 기반 · 규칙식 산출</span>
      </header>

      {/* loading */}
      {isLoading && <p className={styles.reportMessage}>향후 7일 전망을 불러오는 중입니다.</p>}
      {!isLoading && errorMessage && <p className={styles.reportError}>{errorMessage}</p>}

      {/* Contents */}
      {!isLoading && !errorMessage && (
        <div className={styles.sevenDayForecastGrid}>
          
          <article data-kind="production">
            <h4>생산실적 예상</h4>
            <div className={styles.sevenDayForecastValue}>
              <strong>{productionForecast ? formatNumber(productionForecast.total) : "-"}</strong>
              {productionForecast && <span>건</span>}
            </div>
            <p>
              일평균 <strong>{productionForecast
                ? formatDecimal(productionForecast.dailyAverage, 1)
                : "-"}</strong>건
            </p>
            <small>최근 14일 동일 요일 실적 기반</small>
          </article>

          <article data-kind="equipment">
            <h4>예상 평균 가동률</h4>
            <div className={styles.sevenDayForecastValue}>
              <strong>{equipmentForecast
                ? formatDecimal(equipmentForecast.averageRate, 1)
                : "-"}</strong>
              {equipmentForecast && <span>%</span>}
            </div>
            <p>
              저가동 설비 예상 <strong>{equipmentForecast
                ? formatNumber(equipmentForecast.lowCount)
                : "-"}</strong>대
            </p>
            <small title={equipmentForecast
              ? `최저 예상 ${equipmentForecast.minimumName} ${formatDecimal(equipmentForecast.minimumRate, 1)}%`
              : undefined}
            >
              {equipmentForecast
                ? `최저 예상 ${equipmentForecast.minimumName} ${formatDecimal(equipmentForecast.minimumRate, 1)}%`
                : "최근 7일 평일 가동률 데이터 없음"}
            </small>
          </article>

          <article data-kind="delivery">
            <h4>납기 지연 예상</h4>
            <div className={styles.sevenDayForecastValue}>
              <strong>{formatNumber(row?.P50_DELAY_COUNT)}</strong>
              <span>건</span>
            </div>
            <p>
              7일 내 납기 <strong>{formatNumber(row?.TARGET_ORDER_COUNT)}</strong>건
            </p>
            <small>
              대표값 P50 · 잔여 공정별 실측 리드타임 기준
              {toNumber(row?.UNFORECASTABLE_ORDER_COUNT) > 0
                ? ` · 전망 제외 ${formatNumber(row?.UNFORECASTABLE_ORDER_COUNT)}건`
                : ""}
            </small>
          </article>

          <article data-kind="depletion">
            <h4>작업 소진 전망</h4>
            <div className={styles.sevenDayForecastValue}>
              <strong>{hasGrossDepletionDays
                ? formatDecimal(depletionRow?.GROSS_DEPLETION_DAYS, 1)
                : "-"}</strong>
              {hasGrossDepletionDays && <span>일</span>}
            </div>
            <p>
              미완료 <strong>{depletionRow ? formatNumber(depletionRow.INCOMPLETE_COUNT) : "-"}</strong>건
              <i aria-hidden="true">·</i>
              완료 <strong>{depletionRow
                ? formatDecimal(depletionRow.DAILY_AVERAGE_COMPLETED_COUNT, 2)
                : "-"}</strong>건/일
            </p>
            <small title={getDepletionMessage(depletionRow)}>{getDepletionMessage(depletionRow)}</small>
          </article>
        </div>
      )}
    </section>
  );
}
