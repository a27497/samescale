import { DEFAULTS } from "./defaults.ts";

export function buildSettings(overrides: Record<string, unknown>): Record<string, unknown> {
  return { ...DEFAULTS, ...overrides };
}
