import type { MesViewRow } from "@/services/mesApi";
import styles from "../../mes.module.css";
import ProductionResult from "./Cards/01_ProductionResult";
import IncompleteWork from "./Cards/02_IncompleteWork";
import DeliveryRiskSummary from "./Cards/03_DeliveryRiskSummary";
import EquipmentRate from "./Cards/04_EquipmentBias";
import Inspection from "./Cards/05_Inspection";

type SummaryMetricsProps = {
  productionResultRows: MesViewRow[];
  incompleteWorkRows: MesViewRow[];
  deliveryRiskRows: MesViewRow[];
  machineOperationRateWeeklyRows: MesViewRow[];
  inspectionRows: MesViewRow[];
};

export default function SummaryMetrics({
  productionResultRows,
  incompleteWorkRows,
  deliveryRiskRows,
  machineOperationRateWeeklyRows,
  inspectionRows,
}: SummaryMetricsProps) {
  return (
    <section className={styles.overviewMetrics} aria-label="운영 핵심 지표">
      <ProductionResult rows={productionResultRows} />
      <IncompleteWork rows={incompleteWorkRows} />
      <DeliveryRiskSummary rows={deliveryRiskRows} />
      <EquipmentRate rows={machineOperationRateWeeklyRows} />
      <Inspection rows={inspectionRows} />
    </section>
  );
}
