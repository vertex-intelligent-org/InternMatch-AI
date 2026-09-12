import { useState, useRef, useEffect, useCallback } from 'react';
import { generateApplication, getProcessingJob, ApiError,
  cancelProcessingJob,} from '../services/api';

const POLL_INTERVAL_MS = 1500;
const TIMEOUT_MS = 210000; // 210 seconds (safely exceeds RQ 180s worker timeout)
const VISUAL_PROGRESS_INTERVAL_MS = 500;
const VISUAL_PROGRESS_CAP = 94;
const VISUAL_PROGRESS_TIME_CONSTANT_MS = 18000;
const VISUAL_PROGRESS_START = 5;

export function useApplicationGeneration() {
  const [isGenerating, setIsGenerating] = useState(false);
  const [progressPercent, setProgressPercent] = useState(0);
  const [generationError, setGenerationError] = useState(null);
  const [isCancelling, setIsCancelling] = useState(false);

  const isMountedRef = useRef(true);
  const pollTimerRef = useRef(null);
  const visualProgressTimerRef = useRef(null);
  const isPollingRef = useRef(false);
  const startTimeRef = useRef(0);
  const isGeneratingRef = useRef(false);
  const activeJobIdRef = useRef(null);
  const cancelInFlightRef = useRef(false);

  const clearPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    isPollingRef.current = false;
  }, []);

  const clearVisualProgress = useCallback(() => {
    if (visualProgressTimerRef.current) {
      clearInterval(
        visualProgressTimerRef.current
      );
      visualProgressTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      clearPolling();
      clearVisualProgress();
    };
  }, [clearPolling, clearVisualProgress]);

  const cancelGeneration = useCallback(async () => {
    if (cancelInFlightRef.current) {
      return false;
    }

    const activeJobId = activeJobIdRef.current;

    // Before the enqueue response gives us a durable job id we cannot
    // truthfully claim server cancellation. The screen remains protected
    // and the user can retry once the accepted job id is available.
    if (!activeJobId) {
      return false;
    }

    cancelInFlightRef.current = true;

    if (isMountedRef.current) {
      setIsCancelling(true);
    }

    try {
      // Do not stop local polling first. The server is authoritative:
      // only a successful cancellation response permits local teardown.
      await cancelProcessingJob(activeJobId);

      if (activeJobIdRef.current === activeJobId) {
        activeJobIdRef.current = null;
      }

      clearPolling();
    clearVisualProgress();
      isGeneratingRef.current = false;

      if (isMountedRef.current) {
        setIsGenerating(false);
        setProgressPercent(0);
        setGenerationError(null);
      }

      return true;
    } finally {
      cancelInFlightRef.current = false;

      if (isMountedRef.current) {
        setIsCancelling(false);
      }
    }
  }, [clearPolling, clearVisualProgress]);

  const startGeneration = useCallback(
    async (params, onComplete) => {
      // Guard against duplicate/concurrent submissions
      if (isGeneratingRef.current) {
        return;
      }

      clearPolling();
      clearVisualProgress();
      isGeneratingRef.current = true;
    activeJobIdRef.current = null;
      setIsGenerating(true);
      setProgressPercent(
        VISUAL_PROGRESS_START
      );
      setGenerationError(null);
      startTimeRef.current = Date.now();

      visualProgressTimerRef.current =
        setInterval(() => {
          if (
            !isMountedRef.current ||
            !isGeneratingRef.current
          ) {
            return;
          }

          const elapsedMs =
            Date.now() -
            startTimeRef.current;

          const eased =
            1 -
            Math.exp(
              -elapsedMs /
                VISUAL_PROGRESS_TIME_CONSTANT_MS
            );

          const nextProgress =
            Math.min(
              VISUAL_PROGRESS_CAP,
              Math.round(
                VISUAL_PROGRESS_START +
                  (
                    VISUAL_PROGRESS_CAP -
                    VISUAL_PROGRESS_START
                  ) *
                    eased
              )
            );

          setProgressPercent(
            (current) =>
              Math.max(
                current,
                nextProgress
              )
          );
        }, VISUAL_PROGRESS_INTERVAL_MS);

      try {
        const acceptRes = await generateApplication({
          match_id: params.match_id,
          tone: params.tone,
          content_locale: params.content_locale || 'en',
        });
        const activeJobId = acceptRes.job_id;

        activeJobIdRef.current = activeJobId;
        if (!isMountedRef.current || !isGeneratingRef.current) {
          return;
        }

        setProgressPercent(
          (current) =>
            Math.max(current, 8)
        );

        const poll = async () => {
          if (!isMountedRef.current || !isGeneratingRef.current || isPollingRef.current) {
            return;
          }

          // Timeout check (210s)
          if (Date.now() - startTimeRef.current > TIMEOUT_MS) {
            clearPolling();
            clearVisualProgress();
            isGeneratingRef.current = false;
            if (isMountedRef.current) {
              setIsGenerating(false);
              setGenerationError('APPLICATION_GENERATION_TIMEOUT');
            }
            return;
          }

          isPollingRef.current = true;

          try {
            const job = await getProcessingJob(activeJobId);

            if (!isMountedRef.current || !isGeneratingRef.current) {
              return;
            }

            if (job.status === 'queued') {
              setProgressPercent(
                (current) =>
                  Math.max(
                    current,
                    Math.min(
                      job.progress_percent || 0,
                      VISUAL_PROGRESS_CAP
                    )
                  )
              );
              isPollingRef.current = false;
              scheduleNextPoll();
            } else if (job.status === 'processing') {
              setProgressPercent(
                (current) =>
                  Math.max(
                    current,
                    Math.min(
                      job.progress_percent || 0,
                      VISUAL_PROGRESS_CAP
                    )
                  )
              );
              isPollingRef.current = false;
              scheduleNextPoll();
            } else if (job.status === 'completed') {
              clearPolling();
              clearVisualProgress();
              isGeneratingRef.current = false;
              setProgressPercent(100);
              setIsGenerating(false);

              if (onComplete) {
                onComplete(job.result);
              }
            } else if (job.status === 'failed') {
              clearPolling();
              clearVisualProgress();
              isGeneratingRef.current = false;
              setProgressPercent(100);
              setIsGenerating(false);
              setGenerationError('APPLICATION_GENERATION_FAILED');
            }
          } catch (err) {
            if (!isMountedRef.current || !isGeneratingRef.current) {
              return;
            }

            console.warn('Application generation poll error:', err);
            isPollingRef.current = false;

            if (err instanceof ApiError && err.status === 401) {
              clearPolling();
              clearVisualProgress();
              isGeneratingRef.current = false;
              setIsGenerating(false);
              setGenerationError('UNAUTHENTICATED');
            } else {
              // Transient network failure; schedule retry poll
              scheduleNextPoll();
            }
          }
        };

        const scheduleNextPoll = () => {
          clearPolling();
          if (!isMountedRef.current || !isGeneratingRef.current) {
            return;
          }
          pollTimerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
        };

        scheduleNextPoll();
      } catch (err) {
        if (!isMountedRef.current) {
          return;
        }
        console.warn('Failed to enqueue application generation:', err);
        clearPolling();
        clearVisualProgress();
        isGeneratingRef.current = false;
        setIsGenerating(false);

        if (err instanceof ApiError) {
          if (
            err.status === 402 &&
            err.code === 'AI_QUOTA_EXCEEDED'
          ) {
            setGenerationError('AI_QUOTA_EXCEEDED');
          } else if (err.status === 404) {
            setGenerationError('MATCH_NOT_FOUND');
          } else if (err.status === 429) {
            setGenerationError('RATE_LIMITED');
          } else if (err.status === 503) {
            setGenerationError('SERVICE_UNAVAILABLE');
          } else if (err.status === 401) {
            setGenerationError('UNAUTHENTICATED');
          } else {
            setGenerationError('APPLICATION_GENERATION_START_FAILED');
          }
        } else {
          setGenerationError('APPLICATION_GENERATION_START_FAILED');
        }
      }
    },
    [clearPolling]
  );

  return {
    isGenerating,
    isCancelling,
    progressPercent,
    generationError,
    startGeneration,
    cancelGeneration,
  };
}
