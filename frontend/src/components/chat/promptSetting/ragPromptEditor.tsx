import { useEffect, useState } from "react";
import { isAxiosError } from "axios";
import { deleteRagPreset, getDefaultRagRules, saveRagPreset, type RagRules } from "@/services/promptApi";
import type { PromptSelectableRow } from "@/types/prompt";
import styles from "./promptSetting.module.css";

type Props = {
  factory: string;
  repair: boolean;
  selected: number | null;
  author: string;
  rows: PromptSelectableRow[] | null;
  listFailed: boolean;
  onSelect: (id: number | null) => void;
  onEditing: (dirty: boolean) => void;
  onDeleted: (id: number) => void;
  onSaved: (row: PromptSelectableRow) => void;
};

const branchLabels: Record<string, string> = {
  operator: "현장 작업자", maintenance: "정비·보전", engineer: "기술 엔지니어", manager: "관리자",
  troubleshooting: "문제 해결", emergency_action: "긴급 조치", part_identification: "부품 식별",
  root_cause_analysis: "근본 원인 분석", concept_explanation: "개념 설명",
};

export default function RagPromptEditor({ factory, repair, selected, author, rows, listFailed, onSelect, onEditing, onSaved, onDeleted }: Props) {
  const [defaults, setDefaults] = useState<RagRules>({});
  const [requestedSection, setSection] = useState("기본 역할");
  const [changes, setChanges] = useState<RagRules>({});
  const [draftName, setDraftName] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const row = rows?.find(item => item.prompt_no === selected);
  let stored: RagRules = {};
  let invalid = false;
  if (row) {
    try {
      stored = JSON.parse(row.prompt_txt).rag_rules;
      invalid = !stored || typeof stored !== "object" || Array.isArray(stored);
    } catch { invalid = true; }
  }
  const repairKnowhow = "수리 사례 · 와프 현장 노하우";
  const keys = Object.keys(defaults);
  const stages = [
    { title: "기본 지침", keys: repair ? [] : ["기본 역할", "도메인 표기"] },
    { title: "사용자 역할", note: "설정한 역할 하나", keys: repair ? [] : keys.filter(key => key.startsWith("사용자 역할 · ")) },
    { title: "질문 의도", note: "질문에 맞는 의도 하나", keys: repair ? [] : keys.filter(key => key.startsWith("질문 의도 · ")) },
    { title: "적용 범위", keys: [...(!repair && factory === "waff" ? ["와프 현장 노하우"] : []), "매뉴얼 범위"] },
    { title: repair ? "수리 사례 해석" : "답변 근거", keys: repair ? [repairKnowhow]
      : ["응답 규칙", "RAG 규칙", "후속 질문"] },
    { title: "출력 형식", keys: repair ? [] : ["출력 형식"] },
    { title: "답변 표현과 인용", keys: [...(repair ? [] : ["인용 규칙", "인용 예시"]), "답변 스니펫", "그림·래더 인용"] },

  ].map(stage => ({ ...stage, keys: stage.keys.filter(key => key in defaults) }))
    .filter(stage => stage.keys.length > 0);
  const sections = stages.flatMap(stage => stage.keys);
  const section = sections.includes(requestedSection) ? requestedSection : sections[0] ?? "";
  const guidance = section === "출력 형식" ? "답변의 문단 구성과 조건별 출력 형식을 적으세요."
    : section === "기본 역할" ? "모든 일반 RAG 질문에 공통인 업무 범위와 답변 언어를 적으세요."
    : section === "도메인 표기" ? "원문을 유지할 부품명·알람 코드와 작업자에게 보여 줄 표기 예시를 적으세요."
    : section === "응답 규칙" ? "모든 답변에 적용할 공통 원칙을 적으세요. 한 종류의 질문에만 필요한 양식은 출력 형식 선택에서 바꾸세요."
    : section === "후속 질문" ? "이전 대화의 장비나 증상을 이어받는 조건과 새 질문으로 판단할 기준을 적으세요."
    : section === "매뉴얼 범위" ? "현재 장비에 적용되는 매뉴얼 범위를 어떻게 밝힐지 적으세요. 중괄호 안의 값은 실행 시 채워집니다."
    : section.includes("현장 노하우") ? "과거 사례가 현재 증상과 관련될 때 어떤 정보를 보여 줄지 적으세요."
    : section.startsWith("사용자 역할") ? "이 독자의 숙련도, 설명할 용어와 말투를 적으세요. 표와 문단 구성은 출력 형식에서 조정하세요."
    : section.startsWith("질문 의도") ? "이 종류의 질문에 반드시 답할 내용과 추가 확인이 필요한 조건을 적으세요."
    : section === "RAG 규칙" ? "매뉴얼에서 확인할 근거와 근거가 부족할 때의 답변 기준을 적으세요."
    : section.includes("인용") ? "어떤 근거를 사용하고 그 출처를 어디에 표시할지 적으세요."
    : section === "답변 스니펫" ? "일반 답변에서 강조할 내용과 예시를 적으세요."
    : "";
  const name = draftName ?? row?.prompt_name ?? "";
  const rules = Object.fromEntries(keys.map(key => [key, changes[key] ?? stored?.[key] ?? defaults[key]]));
  const dirty = draftName !== null || Object.keys(changes).length > 0;
  const missing = selected !== null && (!row || invalid);
  useEffect(() => { onEditing(dirty || busy || missing); }, [dirty, busy, missing, onEditing]);
  useEffect(() => {
    let active = true;
    getDefaultRagRules().then(value => { if (active) setDefaults(value); })
      .catch(() => { if (active) setError("기본 지시문을 불러오지 못했습니다."); });
    return () => { active = false; };
  }, []);

  function select(id: number | null) {
    onSelect(id);
    setChanges({});
    setDraftName(null);
    setError("");
  }

  async function remove() {
    if (!row || !window.confirm(`공용 저장본 ‘${row.prompt_name}’을 삭제할까요? 모든 사용자의 목록에서 사라집니다.`)) return;
    setBusy(true);
    try {
      await deleteRagPreset(row.prompt_no);
    } catch (err) {
      if (!isAxiosError(err) || err.response?.status !== 404) {
        setError("저장본을 삭제하지 못했습니다. 다시 시도해 주세요.");
        return;
      }
    } finally { setBusy(false); }
    onDeleted(row.prompt_no);
    select(null);
  }

  async function save() {
    setBusy(true);
    setError("");
    const title = name.trim();
    try {
      const id = await saveRagPreset(title, rules, author, title === row?.prompt_name ? row.prompt_no : undefined);
      onSaved({ prompt_no: id, prompt_name: title, prompt_txt: JSON.stringify({ rag_rules: rules }),
        create_user: author, SEL_YN: "N" });
      select(id);
    } catch (err) {
      const detail = isAxiosError(err) && err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "프롬프트를 저장하지 못했습니다.");
    } finally { setBusy(false); }
  }

  return <>
    <section className={styles.promptList} aria-label="프롬프트 목록">
      <h4>프롬프트 목록</h4>
      <label>공용 프롬프트
        <select value={selected ?? ""} disabled={busy} onChange={e => select(e.target.value ? Number(e.target.value) : null)}>
          <option value="">코드 기본값</option>
          {rows?.map(item => <option key={item.prompt_no} value={item.prompt_no}>{item.prompt_name}</option>)}
        </select>
      </label>
      <p className={styles.flowNote}>이번 질문에 적용할 지시문을 용도별로 편집합니다.</p>
      <ol className={styles.ruleList} aria-label="편집 가능한 지시문 조립 순서">
        {stages.map(stage => (
          <li key={stage.title}>
            <h5>{stage.title}{stage.note && <small>{stage.note}</small>}</h5>
            <div className={stage.note ? styles.branches : styles.sequence}>
              {stage.keys.map(key => {
                const modified = rules[key] !== defaults[key];
                return (
                  <button key={key} type="button" aria-label={modified ? `${key}, 코드 기본값에서 변경됨` : key}
                    data-modified={modified || undefined} aria-pressed={section === key} onClick={() => setSection(key)}>
                    {stage.note ? branchLabels[key.split(" · ")[1]] ?? key : key}
                  </button>
                );
              })}
            </div>
          </li>
        ))}
      </ol>
    </section>
    <section className={styles.ragEditor} aria-label="프롬프트 편집">
      <h4>프롬프트 편집</h4>
      <label htmlFor="rag-rule-content">{section}</label>
      {guidance && <p className={styles.flowNote}>{guidance}</p>}
      <textarea id="rag-rule-content" value={rules[section] ?? ""} disabled={busy || !defaults[section] || missing}
        onChange={e => setChanges({ ...changes, [section]: e.target.value })} />
      <label>저장 이름
        <input value={name} disabled={busy} onChange={e => setDraftName(e.target.value)} placeholder="예: 작업 절차 우선" />
      </label>
      <div className={styles.editorActions}>
        {row && <button className={styles.closeButton} type="button" disabled={busy} onClick={remove}>저장본 삭제</button>}
        {dirty && <button className={styles.closeButton} type="button" disabled={busy} onClick={() => select(selected)}>편집 취소</button>}
        <button className={`${styles.closeButton} ${styles.applyButton}`} type="button"
          disabled={busy || !rows || !name.trim() || !Object.keys(defaults).length || missing} onClick={save}>
          {row && name.trim() === row.prompt_name ? "공용 저장본 수정" : "새 이름으로 저장"}
        </button>
      </div>
      {(error || listFailed || missing) && <p role="alert">{error || (listFailed ? "공용 목록을 불러오지 못했습니다." : "선택한 저장본을 확인해 주세요.")}</p>}
    </section>
  </>;
}
