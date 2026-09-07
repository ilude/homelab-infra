import { FetchError } from "./contract.js";

export class Capacity {
  private active = 0;
  constructor(readonly limit: number) {}
  acquire(): () => void {
    if (this.active >= this.limit) throw new FetchError("overloaded", "Service capacity exhausted");
    this.active++;
    let released = false;
    return () => { if (!released) { released = true; this.active--; } };
  }
  get used(): number { return this.active; }
}

// Sequential v1: aborted browser work retains this slot until the backend reports
// it idle. A failed cleanup check quarantines the browser until service restart;
// direct/Jina remain usable. Never release merely because the HTTP client left.
export class BrowserCapacity extends Capacity {
  quarantined = false;
  constructor() { super(1); }
  override acquire(): () => void {
    if (this.quarantined) throw new FetchError("backend_unavailable", "Browser quarantined after unverified cleanup");
    return super.acquire();
  }
}
