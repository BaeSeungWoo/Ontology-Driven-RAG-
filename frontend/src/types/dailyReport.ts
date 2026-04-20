import type { ReactNode } from "react";

export type MetricBadge = "GOOD" | "WATCH" | "WARN";
export type MetricBadgeTone = "good" | "watch" | "warn";

export type DailyReportSectionsRequest = {
  date: string;
  reportId: string;
  locale: string;
};

export type MetricCardData = {
  domain: string;
  domainKo: string;
  badge: MetricBadge;
  badgeTone: MetricBadgeTone;
  value: string;
  unit: string;
  sub1Label: string;
  sub1Value: ReactNode;
  sub2Label: string;
  sub2Value: ReactNode;
};

export type MetricCardOptions = Partial<MetricCardData>;

export type ProductMetricsApi = {
  runningEquipQty: number;
  planQty: number;
  achiveRate: number;
  qty: number;
  totalEquipQty: number;
};

export type ShipmentMetricsApi = {
  planQty: number;
  shipQty: number;
  shipAmt: number;
  delayQty: number;
  leadtimeAVG: number;
};

export type DeliveryMetricsApi = {
  totalCnt: number;
  passCnt: number;
  dangerCnt: number;
  delayCnt: number;
  delvRate: number;
};

export type QualityMetricsApi = {
  totalQty: number;
  qty: number;
  defectQty: number;
  defectRate: number;
  ppm: number;
};

export type EquipmentMetricsApi = {
  totalEquipQty: number;
  runningEquipQty: number;
  runningRate: number;
  alarmEquipQty: number;
  alarmCnt: number;
  status: string;
};

export type AttendanceMetricsApi = {
  total: number;
  work: number;
  absence: number;
  overtime: number;
};

export type MetricsAllApi = {
  product: ProductMetricsApi;
  shipment: ShipmentMetricsApi;
  delivery: DeliveryMetricsApi;
  quality: QualityMetricsApi;
  equipment: EquipmentMetricsApi;
  attendance: AttendanceMetricsApi;
};

export type DailySummaryApi = {
  text: string;
  figures: Array<{
    name: string;
    value: number | string;
  }>;
};

export type DailyAnomalyActionApi = {
  anomaly: string[];
  action: string[];
};

export type DailyAnalysisApi = Array<{
  problem: {
    cause: string[];
    result: {
      summary: string;
      action: string;
    };
  };
}>;

export type DailyReportSectionsApi = {
  summary: DailySummaryApi;
  anomalyAction: DailyAnomalyActionApi;
  metrics: MetricsAllApi;
  analysis: DailyAnalysisApi;
};
