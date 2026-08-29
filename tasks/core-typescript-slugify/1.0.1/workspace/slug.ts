export type Subscribe<T> = (listener: (value: T) => void) => () => void;

export class Subscription<T> {
  private unsubscribe: () => void;
  constructor(subscribe: Subscribe<T>, handler: (value: T) => void) {
    this.unsubscribe = subscribe(handler);
  }
  dispose(): void {
    this.unsubscribe();
  }
}
