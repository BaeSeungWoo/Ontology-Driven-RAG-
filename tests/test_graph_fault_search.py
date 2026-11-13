import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.controller_graph import _equipment_index, _rank


def test_fault_search_prioritizes_matching_state_without_requiring_it(tmp_path):
    question = "펌프가 안 돌아가요"
    blocks = ["급유 펌프 기동 불가", "급유 펌프 사양", "컨베이어 기동 불가"]
    path = tmp_path / "manual.json"
    pages = [dict(page=i, blocks=[body], titles=[]) for i, body in enumerate(blocks, 1)]
    path.write_text(json.dumps(dict(document="manual", pages=pages, tables=[])), encoding="utf8")
    index = _equipment_index(path, 0)
    _, sources = _rank(index, question, question, "dhf8000", "manual", 0, "specific", "",
                       (["급유펌프"], ["기동 불가"]))
    assert [source["excerpt"] for source in sources] == blocks[:2]
