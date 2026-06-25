# pipeline/build_db.py
from pathlib import Path
import argparse
import shutil

from typing import Any

from backend.app.factories.config import CONFIGS
from backend.app.embeddings import save_embedding_meta

from pipeline.ingestion.data_loader import VectorDBBuilder
from pipeline.adapters.site_a import SiteAParser
from pipeline.adapters.site_b import SiteBParser

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

    if reset and Path(config.vector_db.db_path).exists():
        shutil.rmtree(config.vector_db.db_path)
        print(f"[{config.id}] 기존 DB 삭제")


    print(f"\n{'='*50}")
    print(f"  ID: {site_id} | 어댑터: {settings['adapter'].__class__.__name__}")
    print(f"  임베딩: {config.embedding.model} @ {config.get_embedding_base_url()}")
    print(f"  DB 경로: {config.vector_db.db_path}")
    print(f"{'='*50}")

    builder = VectorDBBuilder(config, adapter=settings["adapter"])

    for doc_type, source_dir in settings["sources"].items():
        print(f"\n  [{doc_type}]")
        builder.build_from(source_dir=source_dir, doc_type=doc_type)

    save_embedding_meta(config)
    print(f"\n  [완료] {site_id} 벡터 DB 생성 성공\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=str, default=None)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    build(site_id=args.id, reset=args.reset)
    # for sid in ([args.id] if args.id else list(SITE_SETTINGS.keys())):