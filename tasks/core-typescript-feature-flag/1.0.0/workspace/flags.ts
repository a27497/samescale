export type Request = { kind: "read"; key: string } | { kind: "write"; key: string; value: unknown };

export function validateRequest(input: unknown): Request {
  return input as Request;
}
