interface ReasoningTracker {
  start: () => void;
  finish: () => void;
  duration: () => number | undefined;
  reset: () => void;
}

export const createReasoningTracker = (): ReasoningTracker => {
  let startedAt: number | null = null;
  let elapsedMs: number | undefined;

  return {
    start: () => {
      if (!startedAt) startedAt = Date.now();
    },
    finish: () => {
      if (startedAt && !elapsedMs) elapsedMs = Date.now() - startedAt;
    },
    duration: () => {
      if (elapsedMs) return elapsedMs;
      return startedAt ? Date.now() - startedAt : undefined;
    },
    reset: () => {
      startedAt = null;
      elapsedMs = undefined;
    },
  };
};
