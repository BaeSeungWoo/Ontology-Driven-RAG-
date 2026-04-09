# Tailwind 가이드 (이 프로젝트 기준)

## 왜 이 파일이 필요한가
- JSX 안에 Tailwind 클래스가 길어지면 역할 파악이 어려워집니다.
- 그래서 `src/styles/tailwind-components.css`에 **역할 기반 클래스**를 모아 사용합니다.

## 어디를 보면 되나
1. `src/styles/tailwind-components.css`
- `tw-chat-page`, `tw-chat-toolbar`, `tw-chat-layout`처럼 역할 단위 클래스 정의
- 긴 유틸 조합을 여기서 공통화

2. `src/app/globals.css`
- `@import "../styles/tailwind-components.css";` 로 공통 클래스 로드

3. 실제 사용 예시
- `src/components/chat/chat.tsx`

## 클래스 네이밍 규칙
- 접두사: `tw-`
- 형태: `tw-{화면}-{역할}`
- 예시:
- `tw-chat-page`: 채팅 페이지 루트
- `tw-chat-layout`: 채팅 3열 레이아웃
- `tw-chat-layout-collapsed`: 출처 패널 접힘 상태

## Tailwind vs CSS Module 기준
- Tailwind:
- 레이아웃, 간격, 정렬, 반응형
- 재사용 가능한 UI 골격

- CSS Module:
- 상태 강조, 컴포넌트 내부 세부 스타일
- 테마 색상 믹스, 복잡한 선택자

## 신규 작업 시 권장 순서
1. JSX에서 유틸 조합으로 빠르게 시안 작성
2. 2회 이상 반복되는 조합은 `tailwind-components.css`로 승격
3. 상태 스타일이 복잡하면 CSS Module로 분리

## 간단 예시
```tsx
<div className="tw-chat-page">
  <div className="tw-chat-toolbar">
    <h1 className="tw-chat-title">Ontology-Driven-RAG</h1>
  </div>
</div>
```
