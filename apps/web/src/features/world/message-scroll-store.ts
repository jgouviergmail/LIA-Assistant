export interface MessageScrollPosition {
  anchored: boolean;
  top: number;
}

/** Ephemeral owner UI state; only anchoring changes need a React publication. */
export class MessageScrollStore {
  private position: Readonly<MessageScrollPosition> = { anchored: true, top: 0 };
  private listeners = new Set<() => void>();
  getAnchored = () => this.position.anchored;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  read(): Readonly<MessageScrollPosition> {
    return this.position;
  }
  remember(position: MessageScrollPosition): void {
    const changed = position.anchored !== this.position.anchored;
    this.position = { ...position };
    if (changed) for (const listener of this.listeners) listener();
  }
  reset(): void {
    this.remember({ anchored: true, top: 0 });
  }
}
