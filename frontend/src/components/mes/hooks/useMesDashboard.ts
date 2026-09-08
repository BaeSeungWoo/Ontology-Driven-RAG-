import { useEffect, useState } from "react";
import { getMesDashboardViews, type MesDashboardViews } from "@/services/mesApi";

export function useMesDashboard() {
  const [views, setViews] = useState<MesDashboardViews | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let isMounted = true;

    const loadMesViews = async () => {
      try {
        const result = await getMesDashboardViews();
        if (isMounted) setViews(result);
      } catch (error) {
        if (isMounted) {
          setErrorMessage(
            error instanceof Error ? error.message : "MES 데이터를 불러오지 못했습니다.",
          );
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    loadMesViews();

    return () => {
      isMounted = false;
    };
  }, []);

  return { views, isLoading, errorMessage };
}
