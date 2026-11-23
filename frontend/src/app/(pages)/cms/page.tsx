import { notFound } from "next/navigation";
import Cms from "@/components/cms/cms";

export const dynamic = "force-dynamic";

export default function CmsPage() {
  if (process.env.DAILY_REPORTS_ENABLED !== "true") notFound();
  return (
    <>
      <Cms />
    </>
  );
}
