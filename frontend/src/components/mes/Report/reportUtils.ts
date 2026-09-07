/**
 * MES 조회값을 안전한 숫자로 변환합니다.
 * 숫자로 변환할 수 없는 값은 집계와 표시를 위해 0으로 처리합니다.
 */
export function toNumber(value: unknown): number {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : 0;
}

/**
 * 숫자를 한국어 로케일 형식의 문자열로 표시합니다.
 * maximumFractionDigits로 화면별 소수점 자릿수를 지정할 수 있습니다.
 */
export function formatNumber(value: unknown, maximumFractionDigits = 0): string {
  return new Intl.NumberFormat("ko-KR", { maximumFractionDigits }).format(toNumber(value));
}

/**
 * 날짜형 조회값에서 보고서 비교에 사용할 YYYY-MM-DD 키를 추출합니다.
 * 날짜 형식이 아니면 원본 문자열을 유지합니다.
 */
export function getReportDateKey(value: unknown): string {
  const dateValue = String(value ?? "");
  return /^\d{4}-\d{2}-\d{2}/.test(dateValue) ? dateValue.slice(0, 10) : dateValue;
}
