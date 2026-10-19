import { expect, test } from "vitest";
import { LABELS, SUGGESTED, askMeta, askStatus, pushExchange } from "./ask";
import type { AskResult } from "../types";

const result = (over: Partial<AskResult> = {}): AskResult => ({
  conversation_id: "c1",
  answer: "NTH lead on xG.",
  citations: [{ stat: "xg", value: "NTH 1.42" }],
  verified: true,
  grounded: true,
  source: "llm",
  trace: [{ agent: "match_qa", ms: 4200, tool_calls: 3, ok: true }],
  ...over,
});

test("pushExchange keeps the newest three, newest first", () => {
  expect(pushExchange([], 1)).toEqual([1]);
  expect(pushExchange([3, 2, 1], 4)).toEqual([4, 3, 2]);
  expect(pushExchange([2, 1], 3, 2)).toEqual([3, 2]);
});

test("askStatus tells verified, unverified, not in the data and fallback apart", () => {
  expect(askStatus(result(), "en")).toEqual({ label: "verified", tone: "verified" });
  expect(askStatus(result({ verified: false }), "en")).toEqual({ label: "unverified", tone: "unverified" });
  expect(askStatus(result({ verified: false, grounded: false }), "en")).toEqual({ label: "not in the data", tone: "ungrounded" });
  expect(askStatus(result({ verified: false, grounded: false, source: "template" }), "en")).toEqual({ label: "fallback", tone: "fallback" });
  expect(askStatus(result(), "es").label).toBe("verificado");
  expect(askStatus(result({ verified: false, grounded: false }), "es").label).toBe("sin datos");
  expect(askStatus(result({ verified: false, grounded: false, source: "template" }), "es").label).toBe("respuesta fija");
});

test("askMeta names the match agent with its time and tool calls", () => {
  expect(askMeta(result(), "en")).toBe("Match agent 4.2 s, 3 tools");
  expect(askMeta(result(), "es")).toBe("Agente del partido 4.2 s, 3 herramientas");
  expect(askMeta(result({ trace: [] }), "en")).toBe("");
});

test("four suggested questions and a full label set per language", () => {
  for (const lang of ["en", "es"] as const) {
    expect(SUGGESTED[lang]).toHaveLength(4);
    expect(new Set(SUGGESTED[lang]).size).toBe(4);
    expect(Object.keys(LABELS[lang]).sort()).toEqual(["ask", "error", "placeholder", "suggested", "thinking", "title"]);
  }
  expect(SUGGESTED.en[0]).toBe("Who is creating the most chances?");
});
