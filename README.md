# Ontology-Driven-RAG-
RAG 개발


* **waff-rag-system/**
  ------------------------------------------------------------------------------------------------------
    * **pipeline/** (DB 구축 필요할 때)
        * **parsers/** (파서 전략 (도구))
            * **docling/** (파서 도구 (Docling))
                * `assets.py ` (테이블, 이미지 관련 라이브러리)
                * `toc.py ` (PDF 목차 추출 관련 라이브러리)
                * `refs.py ` (Docling 참조 주소 관련 라이브러리)
                * `build_chunks.py ` (Docling 추출물 -> 청크 조립)
            * **upstage/** (파서 도구 (Upstage))
                * `divise_pdf.py ` (50MB 이상 PDF 분할)
                * `upstage_scan.py ` (Upstage 요청 및 결과 다운로드)
                * `merge_scan_json.py ` (다운로드 결과 -> PDF 별 merge)
            * `docling_parser.py ` (일반 PDF → Markdown 섹션 단위 분할)
            * `upstage_parser.py` (스캔본 → OCR API → element 단위 변환)
        * **data/** (VectorDB 생성 결과물)
            * **A/** (Site ID)
                * **chroma/** (ChromaDB)
                    * `chromaDB(해시값 폴더)` (chromaDB 세그먼트/벡터 저장소)
                    * `chroma.sqlite3` (chromaDB 메타데이터 저장소)
                    * `embedding_meta.json` (임베딩 정보)
                * **manuals/** (Manual 결과물)
                    * **assets/** (이미지, 테이블)
                        * **원본 문서 이름/**
                            * **pictures/**
                                * `0.png`
                            * **tables/**
                                * `0.md`
                    * **extract/** (Docling 추출물)
                        * **batch_json/**
                            * **원본 문서 이름/**
                                * `원본 문서명_part_xxx.json` (각 페이지수에 따라 분할된 json)
                                * `원본 문서명_merge.json` (합쳐진 json)
                    * **inputs/** (원본 문서)
                        * `xxx.pdf` 
                    * **struct/** (구조화된 청크)
                        * `xxx.json` 
        * **adapters/**
            * `base.py` (parse_manual / parse_scanned / parse_drawing)
            * `site_a.py` (도면(PyMuPDF) + 매뉴얼(Docling) + 스캔(Upstage))
            * `site_b.py` (도면(PyMuPDF) + 매뉴얼(Docling·Excel) + 스캔(Upstage))
        * `build_db.py` (VectorDB 생성 실행 부)
        * `chunk_builder.py` (구조화 청크 -> VectorDB 삽입용 청크 변환)
        * `data_loader.py` (site 별 VectorDB 생성 전략 분류 및 실행)
  ------------------------------------------------------------------------------------------------------
    * **backend/** (FastAPI)
        * **app/**
            * `main.py` (FastAPI 엔드포인트 및 라우팅)
            * `service.py` (최종 비즈니스 로직 통합 - Service Layer)
            * **core/** (개발자 A)
                * `llm_handler.py` (LLM Provider 전환 로직 - Ollama/OpenAI)
                * `retriever.py` (Vector/Graph 검색 엔진)
                * `prompt_manager.py` (다중 프롬프트 버전 및 조립 관리)
                * `memory_manager.py` (세션별 대화 기록 관리)
            * **factories/** (개발자 B: Data)
                * `config.py` (공장별 설정 - IP, DB 경로, 페르소나)
                * `data_loader.py` (PDF/도면 파싱 모듈)
            * **database/** ( DB 연결 및 프로시저 결과 )
               * `connection_pool.py`
               * `thread_pool_manager.py`
               * `databse.py`
            * **routers/** ( front 통신 Router )
               * `historyRouter.py`
               * `promptRouter.py`
        * **prompts/** (공유)
            * `registry.json` (전문가/신입/안전 등 프롬프트 버전 저장소)
        * `.env` (API 키 및 환경 변수)
        * `requirements.txt` (필요 라이브러리 목록)
  ------------------------------------------------------------------------------------------------------
    * **frontend/** (Next.js - 개발자 C: UI/UX)
        * **src/**
            * **app/** (App Router - Chat, Admin 페이지)
               * **(pages)/**
                  * **admin/**
                     * `page.tsx`
                  * **chat/**
                     * `page.tsx`
               * `globals.css` 
               * `layout.tsx` ( 메인 레이아웃 )
               * `page.tsx` ( 메인페이지, redirect: Chat  )
            * **components/**
               * **chat/**
                  * `chat.tsx` ( 메인 컴포넌트 )
                  * `chat.module.css` ( chat 전용 css )
                  * `assetPanel.tsx` ( 이미지/표 영역 )
                  * **answer/** ( 답변 영역 )
                     * `answer.tsx` ( LLM 에게 받은 답변을 Markdown 형식으로 렌더 변환 )
                     * `answer.module.css`
                     * `userMessageBubble.tsx` ( 질문 메시지 영역 )
                     * `assistantMessageBuble.tsx` ( 답변 메시지 영역 )
                     * `chatDateDivider.tsx` ( 날짜 구분선 )
                     * `chatDate.ts`
                  * **citation/** ( 인용근거 영역 )
                     * `citation.tsx`
                     * `citation.module.css`
                     * `chunkAsset.tsx` ( 인용근거 내 이미지/표 영역 ) 
                  * **history/** ( 질문/대화 이력 영역 )
                     * `history.tsx`
                     * `history.module.css`
                     * `historyCard.tsx` ( 대화 이력 카드 컴포넌트 )
                  * **promptSetting/** ( 프롬프트 및 LLM 설정 영역 )
                     * `promptSetting.tsx`
                     * `promptSetting.module.css`
                     * `promptListModal.tsx` ( 프롬프트, LLM 모델, LLM 모드 설정 모달 )
                  * **question/** ( 질문 영역 )
                     * `question.tsx`
                     * `question.module.css`
                  * **themeSwitcher/** ( 테마 변경 테스트 옵션 )
                     * `themeSwitcher.tsx`
                     * `themeSwitcher.module.css`
               * **admin/**
                 
            * **constants/** ( 상수 관리 )
               * `llmOptions.ts` ( LLM 모델, 모드 상수 List )
          
            * **hooks/** ( API 호출 및 로직, State 관리 )
               * `useChat.ts` ( 질문전송, 답변 관련 훅 )
               * `useHistoryPanel.ts` ( 질문/대화 이력 관련 훅 )
               * `usePrompt.ts` ( 프롬프트 관련 훅 )
          
            * **services/** ( API 정의 및 백엔드 호출 )
               * `api.ts` ( Axios 설정 )
               * `chatApi.ts` ( 질문전송, 답변 관련 API 정의 )
               * `historyApi.ts` ( 질문/대화 이력 관련 API 정의 )
               * `promptApi.ts` ( 프롬프트 관련 API 정의 )
          
            * **store/** (상태 관리 - 현재 선택된 공장, 세션 ID)
      
            * **styles/** (공장별 테마 - Tailwind)
               * `tailwind-components.css` ( tailwind css 클래스화 )
               * **theme/**
                  * `factory-themes.css` ( 공장별 테마 css )
        * **public/** (공장별 로고, 아이콘)
           * **factoryA/**
           * **factoryB/**
           * **factoryC/**
        * **docs/** ( 유지보수 가이드 문서 )
           * `Tailwind-Guide.md` ( Tailwind 작성 규칙 )
        * `.env.local` ( 테마키 및 API URL )
        * `next.config.js`
        * `docker-compose.yml` (백엔드+프론트엔드 한방 배포)
------------------------------------------------------------------------------------------------------
    * **data/Vector DB**
        * `factory_A/` (공장A 전용 Vector DB 및 매뉴얼)
        * `factory_B/`
        * `factory_C/`
    * `README.md`
