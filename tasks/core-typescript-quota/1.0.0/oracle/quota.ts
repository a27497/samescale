export function retryDelays(attempts: number, baseMs: number, capMs: number): number[] {
  if (![attempts, baseMs, capMs].every(Number.isSafeInteger) || attempts < 1 || baseMs < 1 || baseMs > capMs) {
    throw new RangeError("invalid retry schedule");
  }
  const result: number[] = [];
  let delay = baseMs;
  for (let index = 1; index < attempts; index += 1) {
    result.push(delay);
    delay = delay >= capMs - delay ? capMs : delay + delay;
  }
  return result;
}
