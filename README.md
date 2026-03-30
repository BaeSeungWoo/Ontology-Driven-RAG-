# Ontology-Driven-RAG-
RAG 개발


├── data/               # 샘플 데이터 및 전처리 스크립트  
├── engine/             # RAG 핵심 로직  
│   ├── ingestion.py    # 문서 로드 및 파싱 (PyMuPDF, Docling 등)  
│   ├── indexing.py     # 임베딩 및 Vector DB 저장  
│   └── retrieval.py    # 쿼리 생성 및 검색 (Graph Query, Similarity Search)  
├── prompts/            # 프롬프트 템플릿 관리 (.yaml 또는 .txt)  
├── api/                # FastAPI 등 서빙 관련 코드  
└── tests/              # 유닛 테스트 및 성능 평가(RAGAS 등)  
