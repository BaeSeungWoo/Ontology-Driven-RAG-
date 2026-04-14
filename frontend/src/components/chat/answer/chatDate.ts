// =========================
// 함수
// =========================
/**
 * 기능: 타임스탬프를 날짜 배지 라벨(YYYY년 MM월 DD일)로 변환한다.
 * 목적: 날짜 구분선에서 일자 정보를 일관된 형식으로 표시한다.
 * In: timestamp(number)
 * Out: dateLabel(string)
 */
export const formatDateLabel = (timestamp: number) => {
  const date = new Date(timestamp);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}년 ${m}월 ${d}일`;
};

/**
 * 기능: 타임스탬프를 시각 라벨(hh:mm)로 변환한다.
 * 목적: 사용자 질문 버블의 시각 메타를 간결하게 표시한다.
 * In: timestamp(number)
 * Out: timeLabel(string)
 */
export const formatTimeLabel = (timestamp: number) => {
  const date = new Date(timestamp);
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
};

/**
 * 기능: 날짜 비교용 키(YYYY-MM-DD)를 생성한다.
 * 목적: 메시지 간 날짜 변경 여부를 빠르게 판단한다.
 * In: timestamp(number)
 * Out: dateKey(string)
 */
export const getDateKey = (timestamp: number) => {
  const date = new Date(timestamp);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};
