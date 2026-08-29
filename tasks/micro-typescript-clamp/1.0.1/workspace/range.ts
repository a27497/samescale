export function clamp(value: number, lower: number, upper: number): number {
  return Math.min(lower, Math.max(value, upper));
}
