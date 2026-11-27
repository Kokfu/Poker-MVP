type Candidate = { body: string; controller: AbortController; timer?: ReturnType<typeof setTimeout> };

export class AdvicePrefetch {
  private candidate?: Candidate;

  schedule(body: string) {
    if (this.candidate?.body === body) return;
    this.cancel();
    const candidate: Candidate = { body, controller: new AbortController() };
    candidate.timer = setTimeout(() => {
      candidate.timer = undefined;
      void fetch("/api/coach/advise", {
        method: "POST", headers: { "Content-Type": "application/json", "X-Coach-Speculative": "1" },
        body, signal: candidate.controller.signal,
      }).then(response => response.body?.cancel()).catch(() => { /* A speculative request has no UI result. */ });
    }, 180);
    this.candidate = candidate;
  }

  commit(body: string) {
    // A matching request already on the server can warm the exact solve cache.
    if (this.candidate && (this.candidate.body !== body || this.candidate.timer !== undefined)) this.cancel();
  }

  cancel() {
    if (!this.candidate) return;
    clearTimeout(this.candidate.timer);
    this.candidate.controller.abort();
    this.candidate = undefined;
  }
}
