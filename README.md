# Ontology-Driven-RAG-
RAG 개발


waff-rag-system/
    ├── backend(FastAPI)
        ├── app/
            ├── main.py # FastAPI 엔드포인트 및 라우팅
            ├── core (개발자 A)
                ├── llm_handler.py # LLM Provider (Ollama/OpenAI) 전환 로직
                ├── retriever.py # Vector/Graph 검색 엔진
                ├── prompt_manager.py # 다중 프롬프트 버전 및 조립 관리
                └── memory_manager.py # 세션별 대화 기록(Memory) 관리
            ├── factories(개발자 B : Data)
                └── config.py # 공장별 설정 (IP, DB 경로, 페르소나)
            └── service.py# 최종 비즈니스 로직 통합 (Service Layer)
        ├── data/Vector DB
            ├── factory_A/# 공장A 전용 Vector DB 및 매뉴얼
            ├── factory_B/
            └── factory_C/
        ├── prompts(공유)
            └── registry.json# 전문가/신입/안전 등 프롬프트 버전 저장소
        ├── .env# API 키 및 환경 변수
        └── requirements.txt# 필요 라이브러리 목록
    ├── frontend/Next.js개발자 C (UI/UX)
        ├── src/
            ├── app/# App Router (Chat, Admin 페이지)
            ├── components/# ChatWindow, Message, SourceCard 등
            ├── hooks/# useChat (API 통신 및 스트리밍 로직)
            ├── services/# api.ts (Axios/Fetch 설정)
            ├── store/# 상태 관리 (현재 선택된 공장, 세션 ID)
            └── styles/# 공장별 테마 (Tailwind)
        ├── public/# 공장별 로고, 아이콘
        └── next.config.js
        ├── docker-compose.yml# 백엔드+프론트엔드 한방 배포
    └── README.md