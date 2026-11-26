"""Build factory OCR exports into prepared documents, then search indexes."""
import argparse
from copy import deepcopy
from pathlib import Path
import sys

PIPELINE_ROOT = Path(__file__).resolve().parent
for import_root in (PIPELINE_ROOT.parent, PIPELINE_ROOT.parent / "backend"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from pipeline.ingestion.prepared_documents import (
    document_key, initialize_layout, load_prepared_chunks, prepare_ocr, prepare_ladders, require_empty_indexes,
)


from backend.app.factories.machines import factory_ids


def resolve_build_config(factory_id: str, model_config: str | None = None):
    from backend.app.factories.config import CONFIGS, FACTORY_CONFIGS, get_factory_config

    if factory_id not in factory_ids():
        raise ValueError(f"지원하지 않는 공장: {factory_id}")
    model_key = model_config or (FACTORY_CONFIGS.get(factory_id) or FACTORY_CONFIGS["yunam"]).default_model
    if model_key not in CONFIGS:
        raise ValueError(f"지원하지 않는 모델 설정: {model_key}")
    config = deepcopy(get_factory_config(model_key, factory_id))
    for name, store in config.vector_db.stores.items():
        store.db_path = str(PIPELINE_ROOT / "data" / factory_id / name)
        store.search_path = store.db_path
    return config


def build(factory_id: str, reset: bool = False, *, model_config: str | None = None,
          maintenance_only: bool = False,
          workbook: str | None = None, tacit: str | None = None,
          stage: str = "all", output_root: str | None = None, skip_faiss: bool = False,
          embedding_provider: str | None = None, embedding_url: str | None = None,
          paddleocr_zip: str | None = None, docling_zip: str | None = None) -> None:
    if reset:
        raise ValueError("기존 데이터 삭제는 지원하지 않습니다. 새 --output-root를 지정하세요.")
    if stage not in {"init", "prepare", "ladders", "index", "kg", "multimodal", "all"}:
        raise ValueError(f"지원하지 않는 단계: {stage}")
    config = resolve_build_config(factory_id, model_config)
    if embedding_provider:
        config.embedding.provider = embedding_provider
    if embedding_url:
        config.embedding.base_url = embedding_url
    root = PIPELINE_ROOT / "data" / config.id
    from filelock import FileLock
    destination = Path(output_root).resolve() if output_root else root
    root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(root / ".manual-build.lock"), timeout=0):
        _build_locked(config, root, destination, stage, maintenance_only, workbook, tacit, paddleocr_zip, docling_zip, skip_faiss)


def _build_locked(config, root, destination, stage, maintenance_only, workbook, tacit, paddleocr_zip, docling_zip, skip_faiss):
    if paddleocr_zip:
        if stage not in {"prepare", "all"} or maintenance_only:
            raise ValueError("--paddleocr-zip은 prepare/all 단계에서 사용하세요.")
        from pipeline.ingestion.paddleocr_import import import_zip
        import_zip(Path(paddleocr_zip), root)
    if docling_zip:
        if stage not in {"prepare", "all"} or maintenance_only:
            raise ValueError("--docling-zip은 prepare/all 단계에서 사용하세요.")
        from pipeline.ingestion.paddleocr_import import import_zip
        import_zip(Path(docling_zip), root, "docling")
    if stage == "init":
        initialize_layout(root)
        print(f"폴더 준비 완료 (기존 데이터 유지): {root}")
        return
    if stage == "ladders":
        prepare_ladders(root, config.machines, config.id)
        return
    # Validate before importing models, contacting services, or changing files.
    if not maintenance_only and stage in {"prepare", "all"}:
        prepare_ocr(root, config.machines)
        if stage == "prepare":
            return
    chunks = None if maintenance_only else load_prepared_chunks(root, config.machines, config.id)
    if stage in {"multimodal", "kg"}:
        require_empty_indexes(destination, ("multimodal", "asset/pages") if stage == "multimodal" else
                          ("kg",))
    for name, store in config.vector_db.stores.items():
        store.db_path = str(destination / name)

    from dotenv import load_dotenv
    from pipeline.maintenance_index import build_sources

    load_dotenv()
    if maintenance_only:
        build_sources(config, workbook, tacit)
        return

    if stage == "kg":
        from backend.app.core.llm_handler import LLMProvider
        from pipeline.ingestion.vector_writer import write_kg

        write_kg(config, chunks, config.vector_db.get_db_path("kg"), LLMProvider.get_model(config))
        return

    if stage == "multimodal":
        from backend.app.embeddings import ColpaliEmbedder
        from pipeline.ingestion.data_loader import DataLoader
        from pipeline.ingestion.vector_writer import write_multimodal

        allowed = {document_key(c["metadata"]["source_doc_name"]) for c in chunks
                   if c["metadata"]["document_type"] in {"manual", "controller"}}
        loader = DataLoader(config)
        # Use the same exact document mapping as the prepared text index.
        loader.doc_to_machine = {Path(c["metadata"]["source_doc_name"]).stem:
                                 c["metadata"]["machine_code"] for c in chunks}
        images = []
        for folder, kind in (("manual", "manual"), ("controller", "controller")):
            images.extend(loader.load_image_from(
                {"input": str(root / "inputs/originPDF" / folder)}, kind, destination / "asset",
                allowed_document_names=allowed))
        if not images:
            raise ValueError("멀티모달 빌드 대상 PDF가 inputs/originPDF/manual, inputs/originPDF/controller에 없습니다.")
        embedder = ColpaliEmbedder()
        try:
            write_multimodal(images, config.vector_db.get_db_path("multimodal"), embedder)
        finally:
            embedder.unload()
        return

    from pipeline.ingestion.sync_indexes import sync_indexes
    sync_indexes(config, chunks, destination, skip_faiss=skip_faiss)
    build_sources(config, workbook, tacit)
    print(f"공용 인덱스 생성 완료: {destination} ({len(chunks)} chunks)")


def main(argv=None):
    from backend.app.factories.config import CONFIGS

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory", required=True, choices=factory_ids(),
                        help="입력·출력 폴더와 machine_info를 선택할 공장")
    parser.add_argument("--model-config", choices=CONFIGS,
                        help="답변 생성 LLM 선택 (기본 vllm_config, 임베딩은 공장 설정 유지)")
    parser.add_argument("--stage", choices=("init", "prepare", "ladders", "index", "kg", "multimodal", "all"), default="all")
    parser.add_argument("--output-root", help="인덱스를 생성·갱신할 별도 경로 (입력은 공장 폴더 유지)")
    parser.add_argument("--embedding-provider", choices=("ollama", "openai"), help="임베딩 API 종류")
    parser.add_argument("--embedding-url", help="임베딩 서버 주소 (OpenAI 호환은 /v1 포함)")
    parser.add_argument("--paddleocr-zip", help="원본을 보존하며 inputs/extracted/paddleOCR에 가져올 ZIP")
    parser.add_argument("--docling-zip", help="원본을 보존하며 inputs/extracted/docling에 가져올 ZIP")
    parser.add_argument("--reset", action="store_true", help="사용 불가: 기존 데이터 보존을 위해 거부")
    parser.add_argument("--maintenance-only", action="store_true")
    parser.add_argument("--skip-faiss", action="store_true", help="FAISS 인덱스와 전용 parquet 생성을 생략")
    parser.add_argument("--workbook", help="수리이력 XLS (기본: inputs/repairHistory/*.xls)")
    parser.add_argument("--tacit", help="암묵지 TXT (기본: inputs/knowledge/*.txt)")
    args = parser.parse_args(argv)
    build(factory_id=args.factory, model_config=args.model_config, reset=args.reset, maintenance_only=args.maintenance_only,
          workbook=args.workbook, tacit=args.tacit, stage=args.stage, output_root=args.output_root,
          paddleocr_zip=args.paddleocr_zip, docling_zip=args.docling_zip,
          embedding_provider=args.embedding_provider, embedding_url=args.embedding_url, skip_faiss=args.skip_faiss)


if __name__ == "__main__":
    main()
