import Chat from "@/components/chat/chat";
import { headers } from "next/headers";
import { isIP } from "node:net";

export default async function ChatPage() {
  const requestHeaders = await headers();
  const clientIp = requestHeaders.get("x-forwarded-for")?.split(",")[0].trim().replace(/^::ffff:/i, "") ?? "";
  const today = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date()).replaceAll("-", "");
  const initialQuestioner = isIP(clientIp) ? `${today}-${clientIp}` : "";

  return (
    <>
      <Chat initialQuestioner={initialQuestioner} />
    </>
  )
}
