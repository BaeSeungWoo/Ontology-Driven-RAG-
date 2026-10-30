"""Address recall against gold addresses (recorded in the QA output; not used for generation)."""
import re

ADDR_RE = re.compile(r"[XYRGFKT]\d{1,4}\.\d")


def addr_recall(pred: str, gold_addrs: list[str]) -> dict:
    ga = {a for a in (gold_addrs or []) if ADDR_RE.fullmatch(a)}
    if not ga:
        return {"recall": None, "hit": 0, "total": 0}
    pa = set(ADDR_RE.findall(str(pred)))
    hit = ga & pa
    return {"recall": round(len(hit) / len(ga), 3), "hit": len(hit), "total": len(ga),
            "matched": sorted(hit), "missed": sorted(ga - pa)}
