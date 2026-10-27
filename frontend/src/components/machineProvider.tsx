"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import api from "@/services/api";

export type Machine = {
  machine_code: string;
  machine_name: string;
  machine_controller: string;
  machine_ver: string;
  is_assigned: boolean;
  can_select: boolean;
  is_main_server: boolean;
};

const MachineContext = createContext<{
  machines: Machine[];
  machineCode?: string;
  setMachineCode: (code: string | undefined) => void;
  status: "loading" | "ready" | "error";
  refreshMachines: () => void;
} | null>(null);

export default function MachineProvider({ children }: { children: React.ReactNode }) {
  const [machines, setMachines] = useState<Machine[]>([]);
  const [machineCode, setMachineCode] = useState<string>();
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [revision, setRevision] = useState(0);
  const initialized = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    api.get<Machine[]>("/api/prompts/machines", { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      const assigned = data.find(machine => machine.is_assigned)?.machine_code;
      const master = data.some(machine => machine.is_main_server);
      if (!initialized.current || !master) {
        const initial = master ? data.find(machine => machine.machine_code === process.env.MCODE?.trim() && machine.can_select)?.machine_code : undefined;
        setMachineCode(initial ?? assigned);
      }
      initialized.current = true;
      setMachines(data);
      setStatus("ready");
    }).catch(() => {
      if (!controller.signal.aborted) setStatus("error");
    });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    const refresh = () => setRevision(value => value + 1);
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, []);

  return <MachineContext.Provider value={{ machines, machineCode, setMachineCode, status,
    refreshMachines: () => setRevision(value => value + 1) }}>{children}</MachineContext.Provider>;
}

export function useMachine() {
  const context = useContext(MachineContext);
  if (!context) throw new Error("MachineProvider is required");
  return context;
}
