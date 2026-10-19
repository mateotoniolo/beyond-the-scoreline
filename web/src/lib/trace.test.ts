import { expect, test } from "vitest";
import { formatTrace, traceTotalMs } from "./trace";
import type { AgentStep } from "../types";

const step = (agent: string, ms: number, tool_calls = 0): AgentStep => ({ agent, ms, tool_calls, ok: true });

const steps: AgentStep[] = [
  step("tactical_analyst", 2931),
  step("narrator", 2552),
  step("fact_checker", 1020, 2),
  step("producer", 1),
];

test("formatTrace names each role with its time and tool calls", () => {
  expect(formatTrace(steps, "en")).toEqual(["Analyst 2.9 s", "Narrator 2.6 s", "Fact checker 1.0 s, 2 tools", "Producer"]);
  expect(formatTrace(steps, "es")[2]).toBe("Verificador 1.0 s, 2 herramientas");
  expect(formatTrace([step("fact_checker", 400, 1)], "en")).toEqual(["Fact checker 0.4 s, 1 tool"]);
});

test("traceTotalMs sums the steps and unknown agents keep their raw name", () => {
  expect(traceTotalMs(steps)).toBe(6504);
  expect(formatTrace([step("scout", 1500)], "en")).toEqual(["scout 1.5 s"]);
});
