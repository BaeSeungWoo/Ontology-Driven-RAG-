import { notFound } from "next/navigation";
import Mes from "@/components/mes/mes";

export const dynamic = "force-dynamic";

export default function MesPage() {
  if (process.env.DAILY_REPORTS_ENABLED !== "true") notFound();
  return <Mes />;
}
