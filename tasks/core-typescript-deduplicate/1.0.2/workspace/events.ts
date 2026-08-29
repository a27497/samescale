export function parseCursor(value: string): { offset: number; anchor: string } {
  const [offset, anchor] = value.split("@");
  return { offset: Number(offset), anchor };
}
