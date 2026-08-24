import { SENSITIVE_KEYS } from "./defaults.ts";

export function redact(value: unknown, active = new Set<object>()): unknown {
  if (!value || typeof value !== "object") return value;
  if (active.has(value)) throw new TypeError("circular value");
  active.add(value);
  try {
    if (Array.isArray(value)) {
      const result = new Array(value.length);
      for (let index = 0; index < value.length; index += 1) {
        if (index in value) result[index] = redact(value[index], active);
      }
      return result;
    }
    const result: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) {
      result[key] = SENSITIVE_KEYS.has(key.toLowerCase()) ? "[REDACTED]" : redact(item, active);
    }
    return result;
  } finally {
    active.delete(value);
  }
}
