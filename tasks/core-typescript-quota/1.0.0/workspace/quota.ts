export class Quota {
  public remaining: number;

  constructor(remaining: number) {
    this.remaining = remaining;
  }

  consume(units: number): boolean {
    if (units < this.remaining) {
      this.remaining -= units;
      return true;
    }
    this.remaining -= units;
    return false;
  }
}
