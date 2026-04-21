# pipeline/build_db.py

import argparse
from backend.app.factories.config import CONFIGS
from pipeline.data_loader import VectorDBBuilder
from pipeline.adapters.site_a import SiteAParser
from pipeline.adapters.site_b import SiteBParser

SITE_SETTINGS = {
    "A": {
        "adapter": SiteAParser(),
        "sources": {
            "drawing": {
                "input": "./data/A/drawings/inputs",
                "extract": "./data/A/drawings/extract",
                "struct": "./data/A/drawings/struct",
                "asset": "./data/A/drawings/asset"
            },
            "manual":  {
                "input": "./data/A/manuals/inputs",
                "extract": "./data/A/manuals/extract",
                "struct": "./data/A/manuals/struct",
                "asset": "./data/A/manuals/asset"
            },     # 일반 PDF → Docling
            "scanned": {
                "input": "./data/A/scanned/inputs",
                "extract": "./data/A/scanned/extract",
                "struct": "./data/A/scanned/struct",
                "asset": "./data/A/scanned/asset"
            },     # 스캔본  → Upstage
        },
    },
    "B": {
        "adapter": SiteBParser(),
        "sources": {
            "drawing": {
                "input": "./data/B/drawings/inputs",
                "extract": "./data/B/drawings/extract",
                "struct": "./data/B/drawings/struct",
                "asset": "./data/B/drawings/asset"
            },
            "manual":  {
                "input": "./data/B/manuals/inputs",
                "extract": "./data/B/manuals/extract",
                "struct": "./data/B/manuals/struct",
                "asset": "./data/B/manuals/asset"
            },     # PDF + Excel → Docling / openpyxl
            "scanned": {
                "input": "./data/B/scanned/inputs",
                "extract": "./data/B/scanned/extract",
                "struct": "./data/B/scanned/struct",
                "asset": "./data/B/scanned/asset"
            },     # 스캔본  → Upstage   
        },
    },
}


def build(site_id: str, config_id: str, reset: bool = False):
    """메인 실행 부.
    각 site_id에 따라 정해진 폴더 경로에서 vectorDB를 생성

    config_id로 LLM 플랫폼에 대한 설정 값에 따라 실행.

    Args:
        site_id (str): 공장 id
        config_id (str): LLM 설정 아이디
        reset (bool): vectorDB 재생성 여부
    
    """
    config = CONFIGS.get(config_id)
    settings = SITE_SETTINGS.get(site_id)

    if not config or not settings:
        print(f"[오류] '{site_id}' 설정을 찾을 수 없습니다.")
        return

    print(f"\n{'='*50}")
    print(f"  ID: {site_id} | 어댑터: {settings['adapter'].__class__.__name__}")
    print(f"  임베딩: {config.embedding.model} @ {config.get_embedding_base_url()}")
    print(f"  DB 경로: {config.vector_db.db_path}")
    print(f"{'='*50}")

    builder = VectorDBBuilder(config, adapter=settings["adapter"])

    for doc_type, source_dir in settings["sources"].items():
        print(f"\n  [{doc_type}]")
        builder.build_from(source_dir=source_dir, doc_type=doc_type, reset=reset)

    print(f"\n  [완료] {site_id} 벡터 DB 생성 성공\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site_id", type=str, default=None)
    parser.add_argument("--config_id", type=str, default=None)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    for sid in ([args.site_id] if args.site_id else list(SITE_SETTINGS.keys())):
        build(site_id=sid, config_id=args.config_id, reset=args.reset)