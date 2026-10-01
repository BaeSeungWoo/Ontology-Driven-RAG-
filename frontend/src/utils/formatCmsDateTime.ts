// Preserve the recorded time without timezone conversion; display through whole seconds.
export function formatCmsDateTime(text: string): string {
  return text.replace(
    /\b(\d{4})-(\d{2})-(\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.\d+)?\b/g,
    (_, year, month, day, time) => `${year}년 ${Number(month)}월 ${Number(day)}일 ${time}`,
  );
}
