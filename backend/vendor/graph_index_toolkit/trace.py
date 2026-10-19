"""Bounded neighborhood from the same production ranking, with stored edge provenance.

This is an explanatory selection of neighbors, not a traversal order or complete graph.
"""
import ast
import json
import numpy as np
from scipy import sparse
from . import graphindex as module

EDGE_SEMANTICS = {
    "relation": "추출된 주어–관계–대상; 원문 검토 대상",
    "context": "원본 개체–본문 그래프 연결",
    "passage_table": "원본 본문–표 임베딩 연결",
    "table_table": "원본 표–표 임베딩 연결",
    "direct": "계산된 질문 유사도; 저장된 그래프 간선 아님",
    "fact_match": "질문과 관계의 유사도; 저장된 그래프 간선 아님",
}

def norm(value):
    return ''.join(c if c.isalnum() else ' ' for c in str(value).casefold()).strip()


def export_trace(search, vector, question, final, trace, top_k=3):
    vector = module.unit(np.asarray(vector, dtype=np.float32))
    index = search.index_dir
    name = search.manifest["corpus_name"]
    sims = {k: np.maximum(v @ vector, 0) for k,v in search.vectors.items()}
    table_sim = np.maximum(search.table_emb @ vector, 0)
    dense_p = module.top_positions(sims["chunk"], top_k).tolist()
    dense_t = module.top_positions(table_sim, top_k).tolist()
    ppr_p = module.top_positions(trace["scores"][search.passage_idx], top_k).tolist()
    ppr_t = module.top_positions(trace["scores"][search.table_offset:], top_k).tolist()
    fact_pos = module.top_positions(sims["fact"], 4).tolist()
    facts = []
    for pos in fact_pos:
        triple = ast.literal_eval(search.frames["fact"].iloc[pos]["content"])
        facts.append({"triple":list(triple),"score":round(float(sims["fact"][pos]),5),"sources":[]})
    wanted = {tuple(f["triple"]):f for f in facts}
    directory = module.artifact(index, search.manifest["hipporag_save_dir"])
    path = directory / f"openie_results_ner_{search.manifest['llm_model']}.json"
    # Missing extraction logs do not invalidate retrieval; omit fact provenance.
    opened = json.loads(path.read_text(encoding="utf-8"))["docs"] if path.is_file() else []
    pid = {str(h):p for p,h in enumerate(search.frames["chunk"]["hash_id"])}
    p_sources = set()
    for record in opened:
        for raw in record["extracted_triples"]:
            key = tuple(norm(v) for v in raw)
            if key in wanted and len(wanted[key]["sources"]) < 2:
                pos = pid[record["idx"]]
                row = search.passage_rows[pos]
                wanted[key]["sources"].append({"position":pos,"document":row["source_doc"],"pages":row["pages"]["range"]})
                if len(p_sources) < 3: p_sources.add(pos)
    hash_positions = {str(v): i for i, v in enumerate(search.frames["chunk"]["hash_id"])}
    final_p = {hash_positions[str(r["id"])] for r in final if r["type"] == "passage"}
    final_t = {i for i, t in enumerate(search.tables) if any(r["type"] == "table" and str(r["id"]) == str(t["table_idx"]) for r in final)}
    passages = sorted(set(dense_p + ppr_p) | p_sources | final_p)
    table_positions = sorted(set(dense_t + ppr_t) | final_t)
    g = module.artifact(index, search.manifest["graph"])
    base = sparse.load_npz(g / "hipporag_adjacency.npz").tocsr()
    pt = sparse.load_npz(g / "passage_table.npz").tocsr()
    tt = sparse.load_npz(g / "table_table.npz").tocsr()
    epos = {int(n):i for i,n in enumerate(search.entity_idx)}
    entities = set()
    for f in facts:
        for label in (f["triple"][0],f["triple"][2]):
            node = search.entity_lookup.get(label)
            if node is not None: entities.add(node)
    for pos in passages:
        row = base.getrow(int(search.passage_idx[pos]))
        candidates = [(int(node),float(w)) for node,w in zip(row.indices,row.data) if int(node) in epos]
        for node,_ in sorted(candidates,key=lambda x:(-x[1],x[0]))[:2]:
            if len(entities) < 18: entities.add(node)
    final_keys = {(r["type"],str(r["id"])) for r in final}
    nodes, edges = [], []
    def add_node(identifier, kind, label, content, **kw):
        nodes.append({"id":identifier,"kind":kind,"label":label,"content":content,**kw})
    add_node("query","query","질문",question,dense=False,ppr=False,fact=False,final=False)
    fact_entities = {s for f in facts for s in (f["triple"][0],f["triple"][2])}
    for node in sorted(entities):
        pos = epos[node]
        label = str(search.frames["entity"].iloc[pos]["content"])
        add_node(f"e{node}","entity",label,label,fact=label in fact_entities,dense=False,ppr=False,final=False,
                 seed=round(float(trace["seed"][node]),7))
    for pos in passages:
        row = search.passage_rows[pos]
        hash_id = str(search.frames["chunk"].iloc[pos]["hash_id"])
        add_node(f"p{pos}","passage",f"본문 {pos}",row["text"],document=row["source_doc"],pages=row["pages"]["range"],
                 dense=pos in dense_p,ppr=pos in ppr_p,fact=False,final=("passage",hash_id) in final_keys,
                 cosine=round(float(sims["chunk"][pos]),5),ppr_score=round(float(trace["scores"][search.passage_idx[pos]]),8),
                 dense_rank=dense_p.index(pos)+1 if pos in dense_p else None,ppr_rank=ppr_p.index(pos)+1 if pos in ppr_p else None)
    for pos in table_positions:
        row = search.tables[pos]
        meta = row["metadata"]
        pages = meta.get("page_range",meta.get("page_no",""))
        if isinstance(pages, dict): pages = pages.get("range", "")
        merge = meta.get("merge", {})
        if not meta.get("page_range") and merge.get("is_merged") and merge.get("source_pages"):
            pages = f"{min(merge['source_pages'])}-{max(merge['source_pages'])}"
        if merge.get("page_range"):
            pages = merge["page_range"]
            if isinstance(pages, dict): pages = pages.get("range", "")
        content = row["caption"] + "\n" + " | ".join(row["table"]["header"]) + "\n" + "\n".join(" | ".join(map(str,r)) for r in row["table"]["rows"][:18])
        add_node(f"t{pos}","table",f"표 {row['table_idx']}",content,caption=row["caption"],document=meta.get("document",meta.get("document_file","")),pages=str(pages),
                 dense=pos in dense_t,ppr=pos in ppr_t,fact=False,final=("table",str(row["table_idx"])) in final_keys,
                 cosine=round(float(table_sim[pos]),5),ppr_score=round(float(trace["scores"][search.table_offset+pos]),8),
                 dense_rank=dense_t.index(pos)+1 if pos in dense_t else None,ppr_rank=ppr_t.index(pos)+1 if pos in ppr_t else None)
    ids = {n["id"] for n in nodes}
    def edge(source,target,kind,label="",**kw):
        if source in ids and target in ids:
            edges.append({"id":f"edge{len(edges)}","source":source,"target":target,"kind":kind,"label":label,**kw})
    for i,f in enumerate(facts):
        left = search.entity_lookup.get(f["triple"][0])
        right = search.entity_lookup.get(f["triple"][2])
        if left is not None and right is not None:
            edge(f"e{left}",f"e{right}","relation",f["triple"][1],cosine=f["score"],sources=f["sources"],rank=i+1)
            edge("query",f"e{left}","fact_match",f"관계 {i+1}",cosine=f["score"])
    for pos in passages:
        row = base.getrow(int(search.passage_idx[pos]))
        for node,w in zip(row.indices,row.data):
            if int(node) in entities: edge(f"e{int(node)}",f"p{pos}","context","본문에 등장",weight=round(float(w),4))
        for tab in table_positions:
            weight = float(pt[pos,tab])
            if weight > 0: edge(f"p{pos}",f"t{tab}","passage_table","본문–표",cosine=round(weight,5))
    for i,left in enumerate(table_positions):
        for right in table_positions[i+1:]:
            weight = float(tt[left,right])
            if weight > 0: edge(f"t{left}",f"t{right}","table_table","표–표",cosine=round(weight,5))
    for pos in dense_p: edge("query",f"p{pos}","direct","직접 유사도",cosine=round(float(sims["chunk"][pos]),5))
    for pos in dense_t: edge("query",f"t{pos}","direct","직접 유사도",cosine=round(float(table_sim[pos]),5))
    # Store membership separately so switching views never invents graph edges.
    def view(kind):
        if kind=="overall": return {"nodes":[n["id"] for n in nodes],"edges":[e["id"] for e in edges]}
        if kind=="dense": selected={"query"}|{f"p{p}" for p in dense_p}|{f"t{t}" for t in dense_t}
        elif kind=="ppr": selected={f"p{p}" for p in ppr_p}|{f"t{t}" for t in ppr_t}
        else: selected={"query"}|{f"e{search.entity_lookup[s]}" for s in fact_entities if s in search.entity_lookup}
        allowed=[]
        for e in edges:
            if kind in ("dense","ppr"):
                if e["kind"]=="context" and e["target"] in selected: selected.add(e["source"]);allowed.append(e["id"])
                elif e["source"] in selected and e["target"] in selected and e["kind"] in ("direct","passage_table","table_table"): allowed.append(e["id"])
            elif e["source"] in selected and e["target"] in selected and e["kind"] in ("relation","fact_match"): allowed.append(e["id"])
        return {"nodes":[n["id"] for n in nodes if n["id"] in selected],"edges":allowed}
    result={"id":name,"title":f"{name} · {question[:48]}",
        "question":question,"nodes":nodes,"edges":edges,"facts":facts,"views":{v:view(v) for v in ["overall","dense","triple","ppr"]},
        "index_counts":{"entities":search.manifest["entities"],"passages":search.manifest["passages"],"tables":search.manifest["table_count"]},
        "scope":"Recomputed single-index production retrieval trace; bounded neighborhood, not the complete graph or a cross-index application trace"}
    for v in result["views"].values():
        chosen=set(v["nodes"])
        assert all(e["source"] in chosen and e["target"] in chosen for e in edges if e["id"] in v["edges"])
    return result
