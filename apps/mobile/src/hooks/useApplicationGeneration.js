import { useState, useRef, useEffect, useCallback } from 'react';
import { generateApplication, getProcessingJob, ApiError } from '../services/api';

const POLL_INTERVAL_MS = 1500;
const TIMEOUT_MS = 210000; // 210 seconds (safely exceeds RQ 180s worker timeout)

export function useApplicationGeneration() {
  const [isGenerating, setIsGenerating] = useState(false);
  const [progressPercent, setProgressPercent] = useState(0);
  const [generationError, setGenerationError] = useState(null);

  const isMountedRef = useRef(true);
  const pollTimerRef = useRef(null);
  const isPollingRef = useRef(false);
  const startTimeRef = useRef(0);
  const isGeneratingRef = useRef(false);

  const clearPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    isPollingRef.current = false;
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      clearPolling();
    };
  }, [clearPolling]);

  const cancelGeneration = useCallback(() => {
    clearPolling();
    isGeneratingRef.current = false;
    if (isMountedRef.current) {
      setIsGenerating(false);
      setProgressPercent(0);
      setGenerationError(null);
    }
  }, [clearPolling]);

  const startGeneration = useCallback(
    async (params, onComplete) => {
      // Guard against duplicate/concurrent submissions
      if (isGeneratingRef.current) {
        return;
      }

      clearPolling();
      isGeneratingRef.current = true;
      setIsGenerating(true);
      setProgressPercent(0);
      setGenerationError(null);
      startTimeRef.current = Date.now();

      try {
        const acceptRes = await generateApplication({
          match_id: params.match_id,
          tone: params.tone,
          content_locale: params.content_locale || 'en',
        });
        const activeJobId = acceptRes.job_id;

        if (!isMountedRef.current || !isGeneratingRef.current) {
          return;
        }

        setProgressPercent(0);

        const poll = async () => {
          if (!isMountedRef.current || !isGeneratingRef.current || isPollingRef.current) {
            return;
          }

          // Timeout check (210s)
          if (Date.now() - startTimeRef.current > TIMEOUT_MS) {
            clearPolling();
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
              setProgressPercent(job.progress_percent);
              isPollingRef.current = false;
              scheduleNextPoll();
            } else if (job.status === 'processing') {
              setProgressPercent(job.progress_percent);
              isPollingRef.current = false;
              scheduleNextPoll();
            } else if (job.status === 'completed') {
              clearPolling();
              isGeneratingRef.current = false;
              setProgressPercent(100);
              setIsGenerating(false);

              if (onComplete) {
                onComplete(job.result);
              }
            } else if (job.status === 'failed') {
              clearPolling();
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
    progressPercent,
    generationError,
    startGeneration,
    cancelGeneration,
  };
}
