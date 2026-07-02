export type PersonaType = "operator" | "maintenance" | "engineer" | "manager";

export const PERSONA_OPTIONS: Array<{ value: PersonaType; label: string }> = [
  { value: "operator", label: "현장 작업자" },
  { value: "maintenance", label: "정비·보전" },
  { value: "engineer", label: "기술 엔지니어" },
  { value: "manager", label: "관리자" },
];
