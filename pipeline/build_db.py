# pipeline/build_db.py

import argparse
from backend.app.factories.config import CONFIGS
from backend.app.factories.machine_setting import load_machine_info_json
from pipeline.data_loader import VectorDBBuilder
from pipeline.adapters.site_a import SiteAParser
from pipeline.adapters.site_b import SiteBParser

# SITE_SETTINGS = {
#     "yunam": {
#         "adapter": SiteAParser(),
#         "sources": {
#             "drawing": {
#                 "input": "./data/yunam/drawings/inputs",
#                 "extract": "./data/yunam/drawings/extract",
#                 "struct": "./data/yunam/drawings/struct",
#                 "asset": "./data/yunam/drawings/asset"
#             },
#             "manual":  {
#                 "input": "./data/yunam/manuals/inputs",
#                 "extract": "./data/yunam/manuals/extract",
#                 "struct": "./data/yunam/manuals/struct",
#                 "asset": "./data/yunam/manuals/asset"
#             },     # 일반 PDF → Docling
#             "scanned": {
#                 "input": "./data/yunam/scanned/inputs",
#                 "extract": "./data/yunam/scanned/extract",
#                 "struct": "./data/yunam/scanned/struct",
#                 "asset": "./data/yunam/scanned/asset"
#             },     # 스캔본  → Upstage
#         },
#     },
#     "yulkok": {
#         "adapter": SiteBParser(),
#         "sources": {
#             "drawing": {
#                 "input": "./data/yulkok/drawings/inputs",
#                 "extract": "./data/yulkok/drawings/extract",
#                 "struct": "./data/yulkok/drawings/struct",
#                 "asset": "./data/yulkok/drawings/asset"
#             },
#             "manual":  {
#                 "input": "./data/yulkok/manuals/inputs",
#                 "extract": "./data/yulkok/manuals/extract",
#                 "struct": "./data/yulkok/manuals/struct",
#                 "asset": "./data/yulkok/manuals/asset"
#             },     # PDF + Excel → Docling / openpyxl
#             "scanned": {
#                 "input": "./data/yulkok/scanned/inputs",
#                 "extract": "./data/yulkok/scanned/extract",
#                 "struct": "./data/yulkok/scanned/struct",
#                 "asset": "./data/yulkok/scanned/asset"
#             },     # 스캔본  → Upstage   
#         },
#     },
# }


def build(site_id: str, reset: bool = False):
    """메인 실행 부.
    각 site_id에 따라 정해진 폴더 경로에서 vectorDB를 생성

    config_id로 LLM 플랫폼에 대한 설정 값에 따라 실행.

    Args:
        site_id (str): 공장 id
        config_id (str): LLM 설정 아이디
        reset (bool): vectorDB 재생성 여부
    
    """
    machine_info = load_machine_info_json()

    config = CONFIGS.get(site_id)
    config.machines = machine_info
    settings = {
        config.id: {
            "adapter": SiteAParser(),
            "sources": {
                "drawing": {
                    "input": f"./data/{config.id}/drawings/inputs",
                    "extract": f"./data/{config.id}/drawings/extract",
                    "struct": f"./data/{config.id}/drawings/struct",
                    "asset": f"./data/{config.id}/drawings/asset"
                },
                "manual": {
                    "input": f"./data/{config.id}/manuals/inputs",
                    "extract": f"./data/{config.id}/manuals/extract",
                    "struct": f"./data/{config.id}/manuals/struct",
                    "asset": f"./data/{config.id}/manuals/asset"
                },
                "scanned": {
                    "input": f"./data/{config.id}/scanned/inputs",
                    "extract": f"./data/{config.id}/scanned/extract",
                    "struct": f"./data/{config.id}/scanned/struct",
                    "asset": f"./data/{config.id}/scanned/asset"
                }
            }
        }
    }
    # settings = SITE_SETTINGS.get(site_id)

    if not config or not settings:
        print(f"[오류] '{site_id}' 설정을 찾을 수 없습니다.")
        return

    print(f"\n{'='*50}")
    print(f"  ID: {site_id} | 어댑터: {settings[config.id]['adapter'].__class__.__name__}")
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
    parser.add_argument("--id", type=str, default=None)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    build(site_id=args.id, reset=args.reset)
    # for sid in ([args.id] if args.id else list(SITE_SETTINGS.keys())):