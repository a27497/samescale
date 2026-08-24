export function retryDelays(attempts: number, baseMs: number, capMs: number): number[] {
  const result: number[] = [];
  for (let index = 0; index < attempts; index += 1) {
    result.push(baseMs * 2 ** index);
  }
  return result;
}
