export function experimentDisplayName(name: string, provenance?: string): string {
  return provenance === 'FIXTURE_OFFLINE'
    ? name.replace(/authoritative/gi, 'offline fixture')
    : name
}
