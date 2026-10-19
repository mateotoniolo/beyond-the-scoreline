import type { AgentStep, Lang } from "../types";

const ROLE: Record<Lang, Record<string, string>> = {
  en: { tactical_analyst: "Analyst", narrator: "Narrator", fact_checker: "Fact checker", producer: "Producer", match_qa: "Match agent" },
  es: { tactical_analyst: "Analista", narrator: "Narrador", fact_checker: "Verificador", producer: "Productor", match_qa: "Agente del partido" },
};
const TOOLS: Record<Lang, [string, string]> = { en: ["tool", "tools"], es: ["herramienta", "herramientas"] };

export const roleName = (agent: string, lang: Lang) => ROLE[lang][agent] ?? agent;

/** "Analyst 2.9 s", "Fact checker 1.0 s, 2 tools"; a step under 100 ms shows its name alone. */
export function formatTrace(trace: AgentStep[], lang: Lang): string[] {
  return trace.map((step) => {
    const bits = [roleName(step.agent, lang)];
    if (step.ms >= 100) bits.push(`${(step.ms / 1000).toFixed(1)} s`);
    const label = bits.join(" ");
    if (!step.tool_calls) return label;
    const [one, many] = TOOLS[lang];
    return `${label}, ${step.tool_calls} ${step.tool_calls === 1 ? one : many}`;
  });
}

export const traceTotalMs = (trace: AgentStep[]) => trace.reduce((sum, step) => sum + step.ms, 0);
