"use client";

import { Fragment, createContext, useContext, useEffect, useRef, useState } from "react";
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
  readiness: "no_documents" | "no_search_data" | "check_failed" | "partial" | "ready";
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
      setStatus("ready");
    }).catch(() => {
      if (!controller.signal.aborted) setStatus("error");
    });
    return () => controller.abort();
  }, [revision, llmModel, factoryId]);

  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, []);

  return <MachineContext.Provider value={{ factoryId, setFactoryId, executionMachineCode: machineCode, personaType, setPersonaType, machines, machineCode, setMachineCode, llmModel, setLlmModel, status: (loadedModel !== llmModel || loadedFactory !== factoryId) && status !== "error" ? "loading" : status,
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
