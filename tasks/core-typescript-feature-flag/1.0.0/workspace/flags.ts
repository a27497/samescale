export function parseFeatureFlag(value: string | undefined, defaultValue = false): boolean {
  return value === undefined ? false : value.toLowerCase() === "true";
}
