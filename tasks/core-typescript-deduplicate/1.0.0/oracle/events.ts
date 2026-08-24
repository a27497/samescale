export function deduplicate(events: string[]): string[] {
  return [...new Set(events)];
}
