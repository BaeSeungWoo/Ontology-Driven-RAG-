import { useId } from "react";
import styles from "./reportTheme.module.css";
import type { ReportModel } from "@/types/report";

type Props = {
  value: ReportModel;
  onChange: (value: ReportModel) => void;
  disabled: boolean;
};

export default function ReportModelSelector({ value, onChange, disabled }: Props) {
  const name = useId();
  return (
    <fieldset className={styles.modelSelector} disabled={disabled} aria-labelledby={`${name}-label`}>
      <span id={`${name}-label`} className={styles.modelLabel}>AI 모델</span>
      <label>
        <input type="radio" name={name} value="ollama_config" checked={value === "ollama_config"} onChange={() => onChange("ollama_config")} />
        Ollama
      </label>
      <label>
        <input type="radio" name={name} value="vllm_config" checked={value === "vllm_config"} onChange={() => onChange("vllm_config")} />
        vLLM (Qwen3-VL)
      </label>
    </fieldset>
  );
}
