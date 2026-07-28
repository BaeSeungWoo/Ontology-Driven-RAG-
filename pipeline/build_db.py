# pipeline/build_db.py
from pathlib import Path
import argparse
import shutil

from typing import Any
from dotenv import load_dotenv

from backend.app.factories.config import CONFIGS
from backend.app.embeddings import save_embedding_meta, ColpaliEmbedder

from backend.app.core.llm_handler import LLMProvider
from pipeline.ingestion.data_loader import DataLoader
from pipeline.ingestion.vector_writer import write_bm25, create_vector_collection, write_chroma, write_faiss, write_kg, write_multimodal
from pipeline.adapters.site_a import SiteAParser
from pipeline.adapters.site_b import SiteBParser

load_dotenv()

def _build_sources(factory_id: str) -> dict[str, Any]:
    return {
        "drawing": {
            "input": f"./data/{factory_id}/drawings/inputs",
            "extract": f"./data/{factory_id}/drawings/extract",
            "struct": f"./data/{factory_id}/drawings/struct",
            "asset": f"./data/{factory_id}/drawings/asset",
        },
        "manual": {
            "input": f"./data/{factory_id}/manuals/inputs",
            "extract": f"./data/{factory_id}/manuals/extract",
            "struct": f"./data/{factory_id}/manuals/struct",
            "asset": f"./data/{factory_id}/manuals/asset",
        },
        "scanned": {
            "input": f"./data/{factory_id}/scanned/inputs",
            "extract": f"./data/{factory_id}/scanned/extract",
            "struct": f"./data/{factory_id}/scanned/struct",
            "asset": f"./data/{factory_id}/scanned/asset",
        },
        "text": {
            "input": f"./data/{factory_id}/texts/inputs",
            "struct": f"./data/{factory_id}/texts/struct",
        },
        "ladder": {
            "input": f"./data/{factory_id}/ladder/inputs",
            "struct": f"./data/{factory_id}/ladder/struct",
        }
    }

def _build_site_settings(factory_id: str) -> dict[str, Any]:
    adapter_map = {
        "yunam": SiteAParser,
        "yulkok": SiteBParser,
    }
    adapter_cls = adapter_map.get(factory_id)
    if adapter_cls is None:
        raise ValueError(f"'{factory_id}'에 대한 adapter가 정의되지 않았습니다.")

    return {
        "adapter": adapter_cls(),
        "sources": _build_sources(factory_id),
    }

def build(site_id: str, reset: bool = False) -> None:
    """메인 실행 부.
    각 site_id에 따라 정해진 폴더 경로에서 vectorDB를 생성

    config_id로 LLM 플랫폼에 대한 설정 값에 따라 실행.

    Args:
        site_id (str): 공장 id
        config_id (str): LLM 설정 아이디
        reset (bool): vectorDB 재생성 여부
    
    """
    config = CONFIGS.get(site_id)
    if not config:
        print(f"[오류] '{site_id}' 설정을 찾을 수 없습니다.")
        return
    settings = _build_site_settings(config.id)

    chroma_db_path = Path(config.vector_db.get_db_path("chroma"))
    bm25_db_path = Path(config.vector_db.get_db_path("bm25"))
    faiss_path = Path(config.vector_db.get_db_path("faiss"))
    kg_path = Path(config.vector_db.get_db_path("kg"))
    multimodal_path = Path(config.vector_db.get_db_path("multimodal"))

    # Reset 시 기존 크로마 DB, bm25 bundle 제거 후 재생성
    if reset and chroma_db_path.exists():
        shutil.rmtree(chroma_db_path)
        print(f"[{config.id}] 기존 DB 삭제")

    if reset and bm25_db_path.exists():
        shutil.rmtree(bm25_db_path)
        print(f"[{config.id}] 기존 BM25 삭제")

    if reset and faiss_path.exists():
        shutil.rmtree(faiss_path)
        print(f"[{config.id}] 기존 FAISS 삭제")

    if reset and kg_path.exists():
        shutil.rmtree(kg_path)
        print(f"[{config.id}] 기존 KG 삭제")
    
    if reset and multimodal_path.exists():
        shutil.rmtree(multimodal_path)
        print(f"[{config.id}] 기존 multimodal 삭제")


    print(f"\n{'='*50}")
    print(f"  ID: {site_id} | 어댑터: {settings['adapter'].__class__.__name__}")
    print(f"  임베딩: {config.embedding.model} @ {config.get_embedding_base_url()}")
    print(f"  DB 경로: {chroma_db_path.parent}")
    print(f"{'='*50}")

    # ------------------------------------------------------------

    builder = DataLoader(config, adapter=settings["adapter"])
    all_chunks = []
    all_img_chunks = []

    for doc_type, source_dir in settings["sources"].items():
        print(f"\n  [{doc_type}]")
        if doc_type == "ladder":
            all_chunks.extend(builder.load_ladder_from(source_dir=source_dir, doc_type=doc_type))
        else:
            all_chunks.extend(builder.load_text_from(source_dir=source_dir, doc_type=doc_type))
            all_img_chunks.extend(builder.load_image_from(source_dir=source_dir, doc_type=doc_type, output_dir=multimodal_path))

    if all_chunks:
        collection = create_vector_collection(config)

        write_chroma(
            collection=collection, 
            chunks=all_chunks, 
            id=config.id,
            db_path=chroma_db_path
        )

        write_bm25(config, all_chunks)

        write_faiss(config=config, chunks=all_chunks, db_path=faiss_path)

        llm = LLMProvider.get_model(config)
        write_kg(config=config, chunks=all_chunks, db_path=kg_path, llm=llm)

    if all_img_chunks:
        embedder = ColpaliEmbedder()
        try:
            write_multimodal(
                chunks=all_img_chunks,
                db_path=multimodal_path,
                embedding=embedder
            )
        finally:
            embedder.unload()

    save_embedding_meta(config=config)
    print(f"\n  [완료] {site_id} 벡터 DB 생성 성공\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=str, default=None)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    build(site_id=args.id, reset=args.reset)
    # for sid in ([args.id] if args.id else list(SITE_SETTINGS.keys())):
