import { formatTrace } from "./trace";
import type { AskResult, Lang } from "../types";

export const MAX_EXCHANGES = 3;

export const SUGGESTED: Record<Lang, string[]> = {
  en: [
    "Who is creating the most chances?",
    "Why did momentum swing after the goal?",
    "How is the away keeper doing?",
    "What changed in the last five minutes?",
  ],
  es: [
    "¿Quién genera más chances?",
    "¿Por qué cambió el momentum después del gol?",
    "¿Cómo viene el arquero visitante?",
    "¿Qué cambió en los últimos cinco minutos?",
  ],
};

export const LABELS: Record<Lang, Record<"title" | "placeholder" | "ask" | "thinking" | "suggested" | "error", string>> = {
  en: {
    title: "Ask the match",
    placeholder: "Ask about the score, a player or a moment",
    ask: "Ask",
    thinking: "Checking the data…",
    suggested: "Suggested questions",
    error: "The desk did not answer; try again.",
  },
  es: {
    title: "Preguntale al partido",
    placeholder: "Preguntá por el resultado, un jugador o un momento",
    ask: "Preguntar",
    thinking: "Revisando los datos…",
    suggested: "Preguntas sugeridas",
    error: "El agente no respondió; probá de nuevo.",
  },
};

export type AskTone = "verified" | "unverified" | "ungrounded" | "fallback";

const STATUS: Record<Lang, Record<AskTone, string>> = {
  en: { verified: "verified", unverified: "unverified", ungrounded: "not in the data", fallback: "fallback" },
  es: { verified: "verificado", unverified: "sin verificar", ungrounded: "sin datos", fallback: "respuesta fija" },
};

/** Newest first, capped: the panel shows the last few exchanges only. */
export function pushExchange<T>(list: T[], item: T, max = MAX_EXCHANGES): T[] {
  return [item, ...list].slice(0, max);
}

export function askStatus(result: AskResult, lang: Lang): { label: string; tone: AskTone } {
  const tone: AskTone =
    result.source !== "llm" ? "fallback" : !result.grounded ? "ungrounded" : result.verified ? "verified" : "unverified";
  return { label: STATUS[lang][tone], tone };
}

/** "Match agent 4.2 s, 3 tools"; empty when the result carries no trace. */
export const askMeta = (result: AskResult, lang: Lang): string => formatTrace(result.trace, lang)[0] ?? "";
