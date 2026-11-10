"use client";

import { Fragment, createContext, useContext, useEffect, useRef, useState } from "react";
import axios from "axios";
import api, { setApiFactory, type FactoryId } from "@/services/api";
import type { LlmModel } from "@/constants/llmOptions";
import type { PersonaType } from "@/constants/personaOptions";

export type Machine = {
  machine_code: string;
  machine_name: string;
  machine_controller: string;
  machine_ver: string;
  is_assigned: boolean;
  can_select: boolean;
  has_documents: boolean;
  readiness: "unchecked" | "no_documents" | "no_search_data" | "check_failed" | "partial" | "ready";
  searchable_document_count: number;
  document_count: number;
  has_ladder: boolean;
  has_electrical: boolean;
  is_main_server: boolean;
};

const MachineContext = createContext<{
  factoryId: FactoryId;
  setFactoryId: (factory: FactoryId) => void;
  executionMachineCode?: string;
  personaType: PersonaType;
  setPersonaType: (persona: PersonaType) => void;
  machines: Machine[];
  llmModel: LlmModel;
  setLlmModel: (model: LlmModel) => void;
  machineCode?: string;
  setMachineCode: (code: string | undefined) => void;
  status: "loading" | "ready" | "error";
  selectionStatus: "idle" | "loading" | "ready" | "error";
  selectionError: string;
  refreshMachines: () => void;
} | null>(null);

export default function MachineProvider({ children }: { children: React.ReactNode }) {
  const [factoryId, setFactory] = useState<FactoryId>("yunam_origin");
  const [personaType, setPersona] = useState<PersonaType>("operator");

  const [loadedFactory, setLoadedFactory] = useState<FactoryId>();
  const [llmModel, setLlmModel] = useState<LlmModel>("vllm_config");
  const [loadedModel, setLoadedModel] = useState<LlmModel>();
  const [machines, setMachines] = useState<Machine[]>([]);
  const [machineCode, setMachineCode] = useState<string>();
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [revision, setRevision] = useState(0);
  const [loadedRevision, setLoadedRevision] = useState(-1);
  const [selection, setSelection] = useState<{ key: string; status: "ready" | "error"; error: string }>();
  const selectionKey = `${factoryId}:${llmModel}:${machineCode}:${revision}`;
  const initialized = useRef(false);

  const setFactoryId = (factory: FactoryId) => {
    if (factory === factoryId) return;
    setApiFactory(factory);
    setPersona("operator");
    initialized.current = false;
    setMachineCode(undefined);
    setMachines([]);
    setStatus("loading");
    setFactory(factory);
  };

  const setPersonaType = (persona: PersonaType) => {
    setPersona(persona);
  };

  useEffect(() => {
    const controller = new AbortController();
    api.get<Machine[]>("/api/prompts/machines", { signal: controller.signal, headers: { "X-Factory-Id": factoryId }, params: { llm_model: llmModel } }).then(({ data }) => {
      if (controller.signal.aborted) return;
      const assigned = data.find(machine => machine.is_assigned && machine.can_select)?.machine_code;
      const master = data.some(machine => machine.is_main_server);
      if (!initialized.current || !master) {
        const initial = master ? data.find(machine => machine.machine_code === process.env.MCODE?.trim() && machine.can_select)?.machine_code : undefined;
        setMachineCode(initial ?? assigned);
      }
      initialized.current = true;
      setMachines(data);
      setLoadedModel(llmModel);
      setLoadedFactory(factoryId);
      setLoadedRevision(revision);
      setStatus("ready");
    }).catch(() => {
      if (!controller.signal.aborted) setStatus("error");
    });
    return () => controller.abort();
  }, [revision, llmModel, factoryId]);

  useEffect(() => {
    if (!machineCode || loadedFactory !== factoryId || loadedModel !== llmModel
      || loadedRevision !== revision || status !== "ready") return;
    const controller = new AbortController();
    const updateMachine = (machine: Machine) => setMachines(previous => previous.map(
      item => item.machine_code === machine.machine_code ? machine : item));
    api.get<Machine>(`/api/prompts/machines/${encodeURIComponent(machineCode)}/readiness`, {
      signal: controller.signal, headers: { "X-Factory-Id": factoryId }, params: { llm_model: llmModel },
    }).then(({ data }) => {
      if (controller.signal.aborted) return;
      updateMachine(data);
      setSelection({ key: selectionKey, status: "ready", error: "" });
    }).catch(error => {
      if (controller.signal.aborted) return;
      const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
      if (detail?.machine) updateMachine(detail.machine);
      if (axios.isAxiosError(error) && error.response?.status === 404 && detail?.machine_code === machineCode) {
        setMachines(previous => previous.filter(item => item.machine_code !== machineCode));
      }
      setSelection({ key: selectionKey, status: "error", error: typeof detail === "string" ? detail
        : detail?.message ?? "선택한 장비의 데이터를 확인하지 못했습니다. 다시 시도해 주세요." });
    });
    return () => controller.abort();
  }, [machineCode, factoryId, llmModel, loadedFactory, loadedModel, loadedRevision, revision, status, selectionKey]);

  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, []);

  return <MachineContext.Provider value={{ factoryId, setFactoryId, executionMachineCode: machineCode, personaType, setPersonaType, machines, machineCode, setMachineCode, llmModel, setLlmModel, status: (loadedModel !== llmModel || loadedFactory !== factoryId) && status !== "error" ? "loading" : status,
    selectionStatus: !machineCode ? "idle" : selection?.key === selectionKey ? selection.status : "loading",
    selectionError: selection?.key === selectionKey ? selection.error : "",
    refreshMachines: () => {
      if (status === "error") setStatus("loading");
      setRevision(value => value + 1);
    } }}><Fragment key={factoryId}>{children}</Fragment></MachineContext.Provider>;
}

export function useMachine() {
  const context = useContext(MachineContext);
  if (!context) throw new Error("MachineProvider is required");
  return context;
}
