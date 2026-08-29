export type Subscribe<T> = (listener: (value: T) => void) => () => void;

export class Subscription<T> {
  private active = true;
  private unsubscribe: (() => void) | undefined;
  constructor(subscribe: Subscribe<T>, handler: (value: T) => void) {
    this.unsubscribe = subscribe(value => { if (this.active) handler(value); });
  }
  dispose(): void {
    if (!this.active) return;
    this.active = false;
    const unsubscribe = this.unsubscribe;
    this.unsubscribe = undefined;
    unsubscribe?.();
  }
}
