export class Quota {
  public remaining: number;

  constructor(remaining: number) {
    this.remaining = remaining;
  }

  consume(units: number): boolean {
    if (units <= 0) throw new RangeError("units must be positive");
    if (units > this.remaining) return false;
    this.remaining -= units;
    return true;
  }
}
