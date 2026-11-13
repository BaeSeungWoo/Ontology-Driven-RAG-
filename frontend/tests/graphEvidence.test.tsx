import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it, vi } from "vitest";
import GraphEvidenceText from "@/components/chat/citation/graphEvidenceText";
import KnowledgeGraphAnswer from "@/components/chat/citation/knowledgeGraphAnswer";
import { streamKnowledgeGraphAnswer } from "@/services/knowledgeGraphApi";

vi.mock("@/services/knowledgeGraphApi", () => ({ streamKnowledgeGraphAnswer: vi.fn() }));

it("renders the cited alarm row with its original headers inside the answer card", () => {
  const row = ["A0068.1", "2546", "2546 공구 교환 RECOVERY 상태입니다.", "C"];
  const source = { index: 5, node_id: "27", document_name: "DHF", page: "340", excerpt: row.join(" | "),
    rows: [["Address", "Symbol", "Alarm", "MC Status"], row, ["A0068.2", "2547", "다른 알람", "M"]]
      .map(cells => cells.map(text => ({ text }))) };
  const select = vi.fn();
  render(<GraphEvidenceText answer={`> [!SUMMARY] 관련 조건\n> “${source.excerpt}” [근거 5]`}
    sources={[source]} selected={5} onSelect={select} />);
  const table = screen.getByRole("table", { name: "근거 5 인용 표" }) as HTMLTableElement;
  expect(Array.from(table.rows[0].cells, cell => cell.textContent)).toEqual(["Address", "Symbol", "Alarm", "MC Status"]);
  expect(Array.from(table.rows[1].cells, cell => cell.textContent)).toEqual(row);
  expect(table.rows.length).toBe(2);
  const button = screen.getByRole("button", { name: "[근거 5]", pressed: true });
  fireEvent.click(button);
  expect(select).toHaveBeenCalledWith(source);
});

it("renders merged manual cells when the search evidence is expanded", async () => {
  vi.mocked(streamKnowledgeGraphAnswer).mockResolvedValue({ answer: "설명 [근거 3]", sources: [{
    index: 3, page: "137", document_name: "조작설명서", excerpt: "공구 교환 | 불가 | 가능",
    rows: [[{ text: "항목", colspan: 2 }, { text: "조건", colspan: 8 }],
      [{ text: "기계상태", rowspan: 2 }, { text: "공구 교환" }, { text: "불가", colspan: 3 }, { text: "가능", colspan: 5 }],
      [{ text: "축 이송" }, { text: "불가", colspan: 3 }, { text: "가능", colspan: 5 }]],
  }] });
  render(<KnowledgeGraphAnswer corpora={["dhf8000"]} messageId={1} question="공구교환" snapshot="id"
    originalAnswer="" onSelectSource={() => {}} onClose={() => {}} />);
  fireEvent.click(await screen.findByText(/검색 근거 1개/));
  fireEvent.click(screen.getByText(/조작설명서/));
  const table = screen.getByRole("table", { name: "근거 3 원문 표" }) as HTMLTableElement;
  expect(table.rows[1].cells[0].rowSpan).toBe(2);
  expect(table.rows[1].cells[2].colSpan).toBe(3);
  expect(table.rows[1].cells[3].colSpan).toBe(5);
});

it("selects the cited node and every sentence sharing that source", () => {
  const select = vi.fn();
  const sources = ["71068", "72992"].map((node_id, i) => ({
    index: i + 1, corpus: "fanuc", node_id, excerpt: "", document_name: "", page: "",
  }));
  function Answer() {
    const [selected, setSelected] = useState<number | null>(null);
    return <GraphEvidenceText answer={"> [!SUMMARY] 매뉴얼에서 확인한 내용\n> 첫 문장.  [근거 1]  [근거 2] 다음 문장. [근거 2]\n\n> [!ACTION] 현장에서 확인할 사항\n> 세 번째 문장. [근거 1]"}
      sources={sources} selected={selected} onSelect={s => { setSelected(s.index); select(s.node_id); }} />;
  }
  const { container } = render(<Answer />);
  expect(screen.getByRole("region", { name: "매뉴얼에서 확인한 내용" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "현장에서 확인할 사항 복사" })).toBeTruthy();
  fireEvent.click(screen.getAllByRole("button", { name: "[근거 1]" })[0]);
  expect(select).toHaveBeenLastCalledWith("71068");
  const marked = () => Array.from(container.querySelectorAll("p[class]"), p => p.textContent);
  expect(marked()).toEqual(["첫 문장.  [근거 1]  [근거 2]", "세 번째 문장. [근거 1]"]);
  fireEvent.click(screen.getAllByRole("button", { name: "[근거 2]" })[1]);
  expect(select).toHaveBeenLastCalledWith("72992");
  expect(marked()).toEqual(["첫 문장.  [근거 1]  [근거 2]", "다음 문장. [근거 2]"]);
});
