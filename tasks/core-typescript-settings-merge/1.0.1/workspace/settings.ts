import { SENSITIVE_KEYS } from "./defaults.ts";

export function redact(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(redact);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, SENSITIVE_KEYS.has(key) ? "[REDACTED]" : item]));
  }
  return value;
}
