import type { ReactNode } from "react";

export type CheckPointSectionsRequest = {
  date: string;
  reportId: string;
  locale: string;
};

export type CheckPointSectionsResponse = {
  Section_01: Section01;
  Section_02: Section02;
  Section_03: Section03;
  Section_04: Section04;
  Section_05: Section05;
  Section_06: Section06;
};

/**
 * Section_01 Cards Type
 */
export type Section01 = {
  summary: MetricsAllApi;
  comment: string;
  keyIssue: string[];
};

/**
 * Section_02 (Production) Type
 */
export type Section02 = {
  summary: ProductMetricsApi[];
  summaryComment: string;
  underperform: UnderperformRowApi[];
  underperformComment: string;
  equipmentBottleneck: EquipmentBottleneckRowApi[];
  equipmentUtilization: EquipmentUtilizationRowApi[];
  equipComment: string;
};

/**
 * Section_03 (Shipping) Type
 * - shipState / delayCause 는 백엔드 컬럼 스펙이 아직 유동적이어서
 *   key-value row 형태로 우선 수용한다.
 */
export type Section03 = {
  summary: ShipmentMetricsApi[];
  summaryComment: string;
  shipState: ShipmentStatusRowApi[];
  shipStateComment: string;
  delayCause: DelayCauseRowApi[];
  delayCauseComment: string;
};

export type Section04 = {
  summary: DeliveryMetricsApi[];
  summaryComment: string;
  issues: DeliveryIssueRowApi[];
  issuesComment: string;
};

export type Section05 = {
  summary: QualityMetricsApi[];
  summaryComment: string;
  processQual: QualityProcessRowApi[];
  processQualComment: string;
  defect: QualityDefectCompositionRowApi[];
  defectComment: string;
  lisk: QualityRiskRowApi[];
  liskComment: string;
  custImpact: QualityCustomerImpactRowApi[];
  custImpactComment: string;
};

export type Section06 = {
  summary: EquipmentMetricsApi[];
  summaryComment: string;
  alram: EquipAlarmRowApi[];
  alramComment: string;
  effect: EquipEffectRowApi[];
  effectComment: string;
};

export type DeliveryIssueRowApi = {
  orderNo: string;
  orderDetailNo: number;
  itemName: string;
  delayDay: number;
  requireQty: number;
  cause: string;
  process: string;
  rank: string;
  actionDate: string;
  part: string;
};

export type QualityProcessRowApi = {
  defectProc: string;
  equipName: string;
  processCode: string;
  processName: string;
  defectQty: number;
  defectRate: number;
};

export type QualityDefectCompositionRowApi = {
  result: string;
  defectQty: number;
  defectRatio: string;
};

export type QualityRiskRowApi = {
  orderNo: string;
  orderDetailNo: number;
  itemCode: string;
  itemName: string;
  customerName: string;
  delvDate: string;
  defectQty: number;
  result: string;
  liskRate: number;
  danger: string;
};

export type QualityCustomerImpactRowApi = {
  inspNum: string;
  workNum: string;
  orderNo: string;
  orderDetailNo: number;
  itemCode: string;
  itemName: string;
  defectType: string;
  cause: string;
  defectQty: number;
  customerName: string;
};

export type EquipAlarmRowApi = {
  equipCode: string;
  equipName: string;
  alramCode: string;
  alramMessage: string;
  action: string;
};

export type EquipEffectRowApi = {
  equipCode: string;
  equipName: string;
  effect: string;
  effectTime: string;
  stopTime: string;
};

export type ShipmentStatusRowApi = {
  orderNo: string;
  orderDetailNo: number;
  customerName: string;
  itemCode: string;
  itemName: string;
  planQty: number;
  shipQty: number;
  remainQty: number;
  shipState: string;
  lateDay: number;
};

export type DelayCauseRowApi = {
  orderNo: string;
  customerName: string;
  itemName: string;
  delayQty: number;
  delayCause: string;
};

export type UnderperformRowApi = {
  orderNo?: string;
  seqNo?: number;
  processSeq?: number;
  lotNo: string;
  itemCode: string;
  itemName: string;
  processName: string;
  equipmentCode: string;
  equipmentName: string;
  planQty: number;
  actualQty: number;
  achiveRate: number;
  shortageQty: number;
  cause: string;
};

export type EquipmentBottleneckRowApi = {
  equipmentCode: string;
  equipmentName: string;
  requiredTime: number;
  availableTime: number;
  overTime: number;
  utilization: number;
};

export type EquipmentUtilizationRowApi = {
  equipmentCode: string;
  equipmentName: string;
  availableTime: number;
  runTime: number;
  standardTime: number;
  equipLoss: number;
  workLoss: number;
  planLoss: number;
  utilizationRate: number;
  planRate: number;
  efficiency: number;
};

export type MetricBadge = "GOOD" | "WATCH" | "WARN";
export type MetricBadgeTone = "good" | "watch" | "warn";

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
