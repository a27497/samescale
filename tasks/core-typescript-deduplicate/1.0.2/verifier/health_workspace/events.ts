export function parseCursor(value: string): { offset: number; anchor: string } {
  const match = /^(0|[1-9]\d*)@([A-Za-z0-9_-]+)$/.exec(value);
  if (!match) throw new TypeError("invalid cursor");
  const offset = Number(match[1]);
  if (!Number.isSafeInteger(offset)) throw new TypeError("unsafe cursor offset");
  return { offset, anchor: match[2] };
}
