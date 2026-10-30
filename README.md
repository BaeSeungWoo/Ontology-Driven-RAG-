# Ontology-Driven-RAG-
RAG 개발


* **waff-rag-system/**
  ------------------------------------------------------------------------------------------------------
    * **pipeline/** (DB 구축 필요할 때)
        * **parsers/**
            * `mnemonic_ladder.py` (LST 래더 파싱)
        * **ingestion/**
            * `paddleocr_import.py`, `docling_import.py` (외부 추출 결과 읽기)
            * `prepared_documents.py`, `chunk_refiner.py` (문서 연결·표준 청크 변환)
            * `data_loader.py` (멀티모달용 원본 PDF 페이지 렌더링)
        * **data/{factory}/** (공장별 원본과 빌드 결과)
            * **inputs/** (보존할 입력)
                * **manuals/** (매뉴얼 PDF)
                * **controllers/** (컨트롤러 PDF)
                * **electricals/** (전기도면 PDF)
                * **ladders/** (LST, LAD 원본)
                * **repairHistory/** (수리이력 XLS)
                * **knowledge/** (암묵지 TXT)
                * **extracted/paddleocr/{문서}/** (PaddleOCR 결과와 관련 이미지)
                * **extracted/docling/{문서}/** (Docling struct·asset·extract 원본)
            * **struct/documents/** (문서별 표준 청크 JSONL)
            * **struct/ladders/** (LST 파서의 중간 결과)
            * **asset/** (서비스용 이미지·표; 멀티모달 페이지는 pages/)
            * **chroma/**, **bm25/**, **faiss/** (공용 검색 인덱스)
            * **electrical/** (전기도면 전용 인덱스)
            * **kg/** (별도 지식그래프)
            * **multimodal/** (별도 페이지 이미지 검색 인덱스)
        * `build_db.py` (외부 추출물 전처리 / 표준 청크 기반 인덱싱)
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
20260825

## 공장별 OCR 빌드

빌드는 외부 추출물만 읽으며 원본 PDF를 다시 OCR하지 않습니다. 기존 Docling·Upstage
PDF 추출 코드와 사이트 어댑터는 제거했습니다. Docling 결과 JSONL을 읽는 데
Docling 실행 패키지는 필요하지 않습니다. PDF 원문 조회, 멀티모달 렌더링, 전기도면
엔진이 쓰는 PDF 처리 기능과 의존성은 유지합니다. 기존 파일은 자동 이동하거나
삭제하지 않으며, 예전 `manuals/inputs`, `scanned`, `shared/knowledge/inputs`를
새 빌드 입력에 자동 혼합하지 않습니다. 기존 검색 서비스와 전기도면 설정도
현재 데이터를 계속 참조합니다. 새 결과를 서비스로 전환하는 작업은 별도입니다.

저장소 루트에서 실행합니다. 공장은 필수 옵션 `--factory yunam|yulkok|poongsan`으로
선택합니다. 폴더와 machine_info, 컬렉션은 공장을 따릅니다. 선택 옵션
`--model-config`는 답변 생성 LLM만 선택합니다. 모든 공장의 기본 모델은
`vllm_config`입니다. 예: `--factory yunam --model-config ollama_config`,
`--factory yunam --model-config vllm_config`, `--factory yulkok --model-config vllm_config`.
기존 `--id` 옵션은 제거했습니다.

`CONFIGS`는 모델 선택, `FACTORY_CONFIGS`는 공장별 경로·검색 설정·임베딩을 관리합니다.
LLM을 바꿔도 공장 데이터와 임베딩은 바뀌지 않습니다. 신규 3개 공장은 빌드·검색 모두
vLLM 임베딩(`http://127.0.0.1:8101/v1`, `qwen3-embedding:8b`)을 사용합니다.
연암(구)은 별도 선택 항목으로 복구했으며 기존 `yunam_origin` 데이터와 `yunam` 컬렉션,
Ollama `.179` 임베딩을 사용합니다. 기존 이력의 `yunam(origin)` 식별자도 유지합니다.
연암(구)의 전기도면은 `backend/vendor/electrical_qa_legacy`의 고정된 구버전 엔진과
`config.json`을 사용합니다. 기존 공용 electrical 데이터, 기존 결과·미리보기 경로를 유지합니다.
신규 3개 공장은 `backend/vendor/electrical_qa`의 현재 엔진을 사용합니다.
구버전 기준 커밋과 파일 지문은 `electrical_qa_legacy/SNAPSHOT.json`에 기록되어 있으며,
신규 기능 변경 시 legacy 복사본은 수정하지 않습니다.
신규 공장에서 연암(구)으로 자동 전환하는 데모 우회는 사용하지 않습니다.
신규 공장의 정비·보전·관리자 기능은 공장별 연결 준비 전까지 비활성화합니다.
기술 엔지니어는 공장별 전기도면 인덱스가 검증된 설비에서 사용할 수 있습니다.

SSH 터널은 `ssh -N -p 10521 -L 8100:127.0.0.1:8000 -L 8101:127.0.0.1:8001 work@max.gntp.or.kr`로 연결합니다.
8100은 답변 생성, 8101은 임베딩용입니다. 빌드에서만 임베딩 연결을 변경하려면
`--embedding-provider openai --embedding-url http://127.0.0.1:8101/v1`을 사용할 수 있습니다.
이 옵션은 운영 검색 설정을 자동 변경하지 않으므로 검색도 빌드와 같은 모델·API로 맞춰야 합니다.

```powershell
# 폴더만 생성. 기존 파일은 그대로 유지.
python -m pipeline.build_db --factory yulkok --stage init

# PaddleOCR ZIP 보존·가져오기 → struct/documents + asset
python -m pipeline.build_db --factory yulkok --stage prepare --paddleocr-zip C:/Users/User/Downloads/yulkok_M001_M005_PaddleOCR_non_electrical_20261030.zip

# 이미 가져온 PaddleOCR 결과 전처리 (같은 결과는 덮어쓰지 않고 재사용)
python -m pipeline.build_db --factory yulkok --stage prepare

# Docling ZIP 추가. 준비된 PaddleOCR과 Docling을 함께 전처리.
python -m pipeline.build_db --factory yulkok --stage prepare --docling-zip C:/Ontology-Driven-RAG-/pipeline/data/yulkok/inputs/ocr/yulkok_M001_M005_Docling_missing10_20261030.zip

# inputs/ladders/*.LST → struct/ladders + struct/documents
python -m pipeline.build_db --factory yulkok --stage ladders

# 준비된 전체 struct/documents → Chroma, BM25, FAISS
python -m pipeline.build_db --factory yulkok --stage index --output-root C:/Ontology-Driven-RAG-/pipeline/data/yulkok-next

# 별도 결과물. 각 대상 인덱스가 비어 있어야 함.
python -m pipeline.build_db --factory yulkok --stage kg --output-root C:/Ontology-Driven-RAG-/pipeline/data/yulkok-next
python -m pipeline.build_db --factory yulkok --stage multimodal --output-root C:/Ontology-Driven-RAG-/pipeline/data/yulkok-next
```

`--output-root`는 출력만 변경합니다. 입력과 struct는 원래 공장 폴더에서 읽습니다.
공용 인덱스 생성 후 `inputs/repairHistory/*.xls`, `inputs/knowledge/*.txt`도
기존 수리사례 인덱서로 처리합니다. `--maintenance-only`로 이 단계만 실행할 수 있습니다.
KG와 멀티모달은 공용 인덱스 단계에서 자동 실행하지 않습니다.
멀티모달은 준비된 manual/controller 문서에 대응하는 PDF만 렌더링합니다.
전기도면의 별도 엔진은 이 명령에서 실행하지 않으며 기존 설정을 유지합니다.

### 표준 청크와 문서 연결

`prepare_ocr()`는 제공된 PaddleOCR의 `문서명_0_res.json` 및 `imgs/*.jpg`를
읽습니다. JSON의 page_index는 분할 작업마다 다시 시작할 수 있으므로 파일명의
0 기반 전체 페이지 번호를 사용합니다. 문서 종류·설비 연결은 machine_info가 기준입니다.
PaddleOCR의 manual 7개와 controller 6개 모두 변환합니다. 문서 종류와 추출 형식은
독립적입니다. Docling ZIP은 추가 controller 10개의 struct JSONL과 자산을 제공합니다.
electrical도 공용 전처리 대상에서 제외합니다. ZIP 보고서·숨김 파일·MD·이미지는 모두
입력에 보존하지만 중복 MD, 레이아웃 검출 시각화 PNG는 검색 청크에 넣지 않습니다.
기존 inputs/ocr 폴더는 삭제하거나 자동으로 섞지 않습니다.

표준 청크는 `struct/documents/paddleocr-<문서ID>.jsonl`, 전체 OCR 블록·좌표는
기존 페이지 문맥 확장 기능과 호환되는 `struct/<문서ID>.jsonl`에 저장합니다.
그림 JPG와 HTML 표 내용을 담은 MD는 `asset/paddleocr/<문서ID>/`에 보존합니다.
머리말·꼬리말 등은 검색 청크에서 제외하되 전체 블록에는 보존합니다.
변환 통계와 찾지 못한 그림은 `struct/reports/paddleocr-*.json`에 기록합니다.
같은 결과 재실행은 기존 파일을 변경하지 않고, 내용이 다르면 덮어쓰지 않고 중단합니다.
Docling은 문서 폴더 바로 아래의 `struct/*.jsonl`을 읽고 같은 ChunkRefiner를 사용합니다.
원시 batch/merge JSON을 다시 파싱하지 않습니다. manifest의 문서명과 원본 SHA256을
대조하여 별칭 문서명을 연결하고, 서버 절대 자산 경로는 ZIP 내 실제 파일을 확인한 뒤
`asset/docling/<문서ID>/`로 바꿉니다. 페이지·절 제목·그림·표 정보는 유지합니다.
일부 원본 Docling ID는 서로 다른 페이지에서 반복되므로 원래 ID를 보존하고
문서ID+행 순서로 고유 청크 ID를 만듭니다. 원본 파일은 변경하지 않습니다.

입력 형식은 paddleocr/docling으로 분리하고, 변환 이후는 공통 `struct/documents`
계약으로 합칩니다. `source_type`에 추출 형식, `document_type`에 문서 종류를 저장합니다.
동일 문서에 두 추출물이 있으면 Docling을 우선하며, 이전 PaddleOCR 파일은 삭제하지
않고 공용 인덱스 로딩에서 제외합니다. 아직 변환되지 않은 Docling 입력만 있다는 이유로
기존 PaddleOCR 청크를 검색 대상에서 제외하지 않습니다.
Docling 변환 보고서는 `struct/reports/docling-*.json`에 저장합니다.

수동 반입은 ZIP 안의 문서 폴더를 해당 `inputs/extracted/paddleocr` 또는 `docling`에
그대로 풀면 됩니다. `results` 중간 폴더는 만들지 않습니다. 각 ZIP의 manifest는
해당 종류의 `_reports`에 `manifest_M001_M005.json`, `M006.json` 등 서로 다른 이름으로
보관하세요. 확장자가 `.json`이고 내부 `documents` 목록 형식을 유지하면 파일명은
자유입니다. 기존 manifest를 덮어쓸 필요는 없습니다. CLI ZIP 반입을 사용하면 manifest
내용 해시를 붙인 파일명으로 자동 보관합니다.
빌드에서는 모든 manifest를 함께 읽고 같은 문서는 하나로 합칩니다. 설비 목록은
manifest의 과거 references가 아니라 현재 machine_info를 사용합니다. 같은 문서의
폴더명·페이지 수·원본 PDF 해시가 충돌하면 중단합니다. Windows에서 추출물을
덮어쓸 때 이전 파일이 남아 섞이지 않도록 주의하세요. 기존 생성 결과와 달라진
추출물은 기존 결과 보호 규칙에 따라 덮어쓰기가 거부되며, 자동 증분 교체는 하지 않습니다.
LAD는 원본 보관 대상이며 현재 LST 파서로 읽지 않습니다.

표준 JSONL은 한 줄에 다음 형태의 청크를 저장합니다. 이것은 외부 OCR의 요구
형식이 아니라 변환기와 기존 인덱서 사이의 내부 계약입니다.

```json
{"id":"document-id:page:chunk","page_content":"본문","metadata":{"source_doc_name":"원본 문서명.pdf","page_range":"1-1","container_type":"texts","asset_path":"","section_title":""}}
```

이미지·표 청크는 기존 서비스 규칙대로 `asset_path`를 `pipeline/data` 기준
상대 경로(예: `yulkok/asset/...`)로 저장합니다. 입력 OCR의 원본 파일은 보존합니다.
인덱싱 시 `machine_info_{factory}.json`에서 문서 종류와 모든 설비 코드를 다시
연결하여 `document_type`, `machine_code`, `site_id`, `chunk_id`를 채웁니다.
확장자와 대소문자, Unicode NFC만 정규화하며 부분 문자열로 연결하지 않습니다.
공유 문서는 한 번 저장하고 여러 설비에 연결합니다. 미연결 문서, 분류 충돌,
중복 청크 ID는 빌드를 중단하고 보고합니다. electrical은 공용 인덱스와 KG에서 제외합니다.

기존 인덱스가 있는 출력 경로는 거부하고 `--reset`도 삭제하지 않고 오류를 냅니다.
전체 struct를 대상으로 새 인덱스를 생성하며, 증분 임베딩 재사용은 아직 구현하지
않았습니다. 문서 종류 메타데이터는 보존하지만
이번 변경은 빌드 범위이며, 페르소나별 검색 제한 적용은 별도 작업입니다.


### 공장별 전기도면 인덱스 반입

ZIP 반입 명령 없이 수동 배치할 수도 있습니다.

1. ZIP의 `index/{문서폴더}` 전체를 `pipeline/data/{factory}/electrical/index/`에 복사합니다.
   `manifest.json`, `machine_mapping.json`과 manifest에 등록된 파일을 함께 보관합니다.
2. 대응 원본 PDF를 `pipeline/data/{factory}/inputs/electricals/`에 놓습니다.
3. 현재 `machine_info_{factory}.json`의 해당 설비 `document.electrical`에 같은 문서명이 있어야 합니다.
4. 화면에서 설비 목록을 새로 조회하면(새로고침/창 재활성화), 누락된 `qa_config.json`과
   `qa_profile.json`을 문서 폴더에 자동 생성합니다. 전기도면 QA 요청에서도 같은 확인을 수행합니다.

별도의 상시 폴더 감시나 OCR/임베딩 재빌드는 없습니다. ZIP 루트의 `profile_*.json`은
수동 배치 시 필요하지 않습니다. 문서명과 공통 QA 엔진 설정으로 프로필을 생성합니다.
생성 전에 PDF·인덱스 지문을 확인하며, 복사가 덜 끝났거나 파일이 다르면 준비되지 않은
상태로 두고 다음 조회에서 재시도합니다. 기존 QA 설정과 프로필은 덮어쓰지 않습니다.
설비 번호는 `machine_mapping.json`의 과거 목록이 아니라 현재 machine_info로 연결합니다.


원본 PDF는 `pipeline/data/{factory}/inputs/electricals`, 외부 인덱스는
`pipeline/data/{factory}/electrical/index/{document}`에 보관합니다.
ZIP의 실행 코드나 OCR은 실행하지 않습니다. 기존 파일은 동일 내용이면 재사용하고,
다른 내용이면 덮어쓰지 않고 중단합니다.

```powershell
python -m pipeline.import_electrical --factory yulkok --zip "C:/Ontology-Driven-RAG-/pipeline/data/VC630_5AX_electrical_index_20261030.zip"
```

지원 ZIP에는 `index/{document}/manifest.json`, `machine_mapping.json`, 검색 JSON과
`page_evidence.json`, 루트 `profile_*.json`이 있어야 합니다. PDF가 이미 inputs에 있으면
그 파일의 지문을 검증하고, 없으면 ZIP의 `originals`에서 복사합니다.
반입 시 문서별 `qa_config.json`과 `qa_profile.json`을 생성합니다.
실행 시 현재 `machine_info_{factory}.json`의 `document.electrical` 문서명과 매칭하므로
공유 문서는 인덱스 하나를 여러 설비에서 사용합니다. ZIP에 기록된 설비 번호는
실제 설비 연결의 기준으로 사용하지 않습니다. 일반 임베딩 인덱스 재빌드는 필요 없습니다.

VC630은 율곡 M001·M002·M003에 연결됩니다. 기존 DHF8000 인덱스는 원본을 보존한 채
연암의 electrical로 복사하여 M005·M051에 연결했습니다. 결과와 미리보기 역시 해당
공장의 `electrical/results`, `electrical/previews` 아래에 생성됩니다.
자동 판독 인덱스는 수동 검수 자료로 승격하지 않으며 PDF/파일 지문 및 페이지 범위를
확인한 뒤 기존 답변 근거 검토를 수행합니다.
현재 한 설비에 여러 문서 인덱스가 동시에 연결되면 임의로 하나를 선택하지 않고
문서 선택이 필요하다는 오류를 반환합니다. 복수 도면 선택·통합 질의는 후속 작업입니다.
