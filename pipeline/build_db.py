# pipeline/build_db.py

import argparse
from app.config import CONFIGS
from pipeline.data_loader import VectorDBBuilder
from pipeline.adapters.site_a import SiteAParser
from pipeline.adapters.site_b import SiteBParser

SITE_SETTINGS = {
    "A": {
        "adapter": SiteAParser(),
        "sources": {
            "drawing": "./data/A/drawings",
            "manual":  "./data/A/manuals",     # 일반 PDF → Docling
            "scanned": "./data/A/scanned",     # 스캔본  → Upstage
        },
    },
    "B": {
        "adapter": SiteBParser(),
        "sources": {
            "drawing": "./data/B/drawings",
            "manual":  "./data/B/manuals",     # PDF + Excel → Docling / openpyxl
            "scanned": "./data/B/scanned",     # 스캔본  → Upstage
        },
    },
}


def build(site_id: str, reset: bool = False):
    config = CONFIGS.get(site_id)
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
        print(f"\n  [{doc_type}] {source_dir}")
        builder.build_from(source_dir, doc_type=doc_type, reset=reset)

    print(f"\n  [완료] {site_id} 벡터 DB 생성 성공\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=str, default=None)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    for sid in ([args.id] if args.id else list(SITE_SETTINGS.keys())):
        build(sid, reset=args.reset)