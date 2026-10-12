// 래더 다이어그램 SVG 레이아웃 치수(px). FANUC LADDER-III 화면 비율을 참고했다.
// 전부 이 상수만 바꾸면 전체 그림 크기가 조정된다.
export const MIN_RAIL_GAP = 900;      // 좌/우 레일 사이 최소 간격(입력 회로가 길면 자동으로 늘어남)
export const CELL_WIDTH = 68;         // 접점/코일 한 칸 폭
export const ROW_HEIGHT = 64;         // 한 행 높이(위: 주소, 가운데: 선, 아래: 심볼)
export const WIRE_OFFSET = 28;        // 행 상단 -> 가로선까지 거리
export const JOIN_STUB = 10;          // parallel 진입/진출 세로 연결바 여유폭
export const OUTPUT_BRANCH_GAP = 24;  // 출력 분기(같은 입력 공유) 세로선 ~ 코일 사이 간격
export const LEFT_GUTTER = 44;        // 왼쪽 레일 바깥(net 번호 표시 영역)
export const COMMENT_WIDTH = 260;     // 오른쪽 레일 바깥(코일 코멘트 표시 영역)
export const LABEL_FONT_SIZE = 11;
