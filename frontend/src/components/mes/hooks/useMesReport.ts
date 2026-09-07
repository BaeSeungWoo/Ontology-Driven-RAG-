import { useState } from "react";
import {
  generateMesReport,
  type MesDashboardViews,
  type MesReport,
} from "@/services/mesApi";

export function useMesReport() {
  const [report, setReport] = useState<MesReport | null>(null);
  const [hasRequested, setHasRequested] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const generateReport = async (views: MesDashboardViews | null) => {
    if (!views) return;

    setHasRequested(true);
    setIsLoading(true);
    setErrorMessage("");

    try {
      setReport(await generateMesReport(views));
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "MES 리포트를 생성하지 못했습니다.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  return { report, hasRequested, isLoading, errorMessage, generateReport };
}
