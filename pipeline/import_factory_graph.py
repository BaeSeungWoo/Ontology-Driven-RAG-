"""Import factory graphs and source text used by the application's graph search."""
import argparse
import csv
import json
import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq


DATA = Path(__file__).resolve().parent / "data"


def records(db, table, ids):
    for start in range(0, len(ids), 256):
        batch = [int(i) for i in ids[start:start + 256]]
        placeholders = ",".join("?" for _ in batch)
        rows = dict(db.execute(f"SELECT id, data FROM {table} WHERE id IN ({placeholders})", batch))
        yield from (rows[i] for i in batch)


def export_group(db, source, dest):
    graph = dest / "graph"
    graph.mkdir(parents=True)
    for name in ("integrated_adjacency.npz", "entity_node_indices.npy", "passage_node_indices.npy", "table_idxs.npy"):
        shutil.copyfile(source / "graph" / name, graph / name)
    for kind in ("chunk", "entity"):
        refs = pq.read_table(source / f"{kind}.parquet").to_pydict()
        texts = records(db, "texts", refs["text"])
        if kind == "chunk":
            content = [f"{prefix}:{body}" for prefix, body in zip(refs["prefix"], texts, strict=True)]
        else:
            content = list(texts)
        pq.write_table(pa.table({"content": content}), dest / f"{kind}_content.parquet")

    corpus_ids = np.load(source / "corpus.npy", allow_pickle=False)
    with (dest / "corpus.json").open("w", encoding="utf8") as out:
        out.write("[")
        for i, record in enumerate(records(db, "payloads", corpus_ids)):
            if i:
                out.write(",\n")
            out.write(record)
        out.write("]")
    refs = pq.read_table(source / "tables.parquet").to_pydict()
    if np.load(graph / "table_idxs.npy").tolist() != refs["table_idx"]:
        raise ValueError(f"Table order mismatch in {source}")
    with (dest / "tables.jsonl").open("w", encoding="utf8") as out:
        for i, record in enumerate(records(db, "payloads", refs["payload"])):
            row = json.loads(record)
            row.update(table_idx=refs["table_idx"][i], source_table_idx=refs["source_table_idx"][i])
            row["metadata"]["merge"]["source_table_indices"] = [refs["merge_source"][i]]
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    manifest = {"graph": "graph", "text_corpus": "corpus.json", "tables": "tables.jsonl"}
    (dest / "manifest.json").write_text(json.dumps(manifest), encoding="utf8")


def import_delivery(package, factory, destination):
    with (package / "equipment.csv").open(encoding="utf-8-sig", newline="") as file:
        machines = {}
        for row in csv.DictReader(file):
            if row["factory"] == factory and row["status"] == "ready":
                match = re.fullmatch(rf"groups/{re.escape(factory)}/(G[0-9]+)", row["shared_group_path"])
                if not match or row["equipment_code"] in machines:
                    raise ValueError(f"Invalid equipment mapping: {row}")
                machines[row["equipment_code"]] = match[1]
    if not machines:
        raise ValueError(f"No ready equipment for {factory}")
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as tmp, closing(sqlite3.connect(
        (package / "shared.sqlite3").resolve().as_uri() + "?mode=ro", uri=True
    )) as db:
        stage = Path(tmp) / "delivery"
        for group in sorted(set(machines.values())):
            export_group(db, package / "groups" / factory / group, stage / group)
        (stage / "machines.json").write_text(json.dumps(machines, indent=2), encoding="utf8")
        stage.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="Extracted equipment_delivery directory")
    parser.add_argument("factory", choices=("yunam", "poongsan", "yulkok"))
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    import_delivery(args.package, args.factory, args.destination or DATA / args.factory / "graph/delivery")
