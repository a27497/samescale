export type Request = { kind: "read"; key: string } | { kind: "write"; key: string; value: unknown };

export function validateRequest(input: unknown): Request {
  if (input === null || typeof input !== "object" || Array.isArray(input)) throw new TypeError("invalid request");
  const record = input as Record<string, unknown>;
  const own = (key: string) => Object.prototype.hasOwnProperty.call(record, key);
  if (!own("kind") || !own("key") || typeof record.key !== "string" || record.key.trim() === "") {
    throw new TypeError("invalid request");
  }
  if (record.kind === "read" && Object.keys(record).length === 2) return { kind: "read", key: record.key };
  if (record.kind === "write" && own("value") && Object.keys(record).length === 3) {
    return { kind: "write", key: record.key, value: record.value };
  }
  throw new TypeError("invalid request");
}
