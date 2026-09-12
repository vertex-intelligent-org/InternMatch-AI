import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import {
  ApiError,
  cancelProcessingJob,
  getProcessingJob,
} from '../services/api';

const POLL_INTERVAL_MS = 1200;

const wait = (milliseconds) =>
  new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });

const isCancelledJob = (job) =>
  job?.status === 'failed' &&
  job?.result?.cancelled === true;

const isQuotaExceededJob = (job) =>
  job?.status === 'failed' &&
  job?.result?.error?.code ===
    'AI_QUOTA_EXCEEDED';

export function useCancellableAIJob() {
  const [isProcessing, setIsProcessing] =
    useState(false);
  const [isCancelling, setIsCancelling] =
    useState(false);
  const [progressPercent, setProgressPercent] =
    useState(0);
  const [pollError, setPollError] =
    useState(null);

  const mountedRef = useRef(true);
  const processingRef = useRef(false);
  const activeJobIdRef = useRef(null);
  const generationRef = useRef(0);
  const jobReadyRef = useRef(null);
  const cancelPromiseRef = useRef(null);

  useEffect(() => {
    return () => {
      mountedRef.current = false;
      generationRef.current += 1;
    };
  }, []);

  const publishProcessingState = useCallback(
    (value) => {
      processingRef.current = value;

      if (mountedRef.current) {
        setIsProcessing(value);
      }
    },
    []
  );

  const publishTerminalState = useCallback(
    (generation, progress = 100) => {
      if (
        generation !== generationRef.current
      ) {
        return;
      }

      activeJobIdRef.current = null;
      jobReadyRef.current = null;
      publishProcessingState(false);

      if (mountedRef.current) {
        setProgressPercent(progress);
        setPollError(null);
      }
    },
    [publishProcessingState]
  );

  const runAIJob = useCallback(
    async (startRequest) => {
      if (
        typeof startRequest !== 'function'
      ) {
        throw new TypeError(
          'startRequest must be a function.'
        );
      }

      if (processingRef.current) {
        return {
          status: 'busy',
          result: null,
        };
      }

      const generation =
        ++generationRef.current;

      publishProcessingState(true);
      activeJobIdRef.current = null;

      if (mountedRef.current) {
        setIsCancelling(false);
        setProgressPercent(0);
        setPollError(null);
      }

      let resolveJobReady;

      const jobReadyPromise = new Promise(
        (resolve) => {
          resolveJobReady = resolve;
        }
      );

      jobReadyRef.current =
        jobReadyPromise;

      try {
        const accepted =
          await startRequest();

        if (
          generation !==
          generationRef.current
        ) {
          resolveJobReady(null);

          return {
            status: 'superseded',
            result: null,
          };
        }

        const jobId =
          typeof accepted?.job_id ===
          'string'
            ? accepted.job_id.trim()
            : '';

        if (!jobId) {
          resolveJobReady(null);

          throw new Error(
            'AI job did not return a valid job_id.'
          );
        }

        activeJobIdRef.current = jobId;
        resolveJobReady(jobId);

        while (
          generation ===
          generationRef.current
        ) {
          let job;

          try {
            job =
              await getProcessingJob(
                jobId
              );

            if (
              generation !==
              generationRef.current
            ) {
              return {
                status: 'superseded',
                result: null,
              };
            }

            if (mountedRef.current) {
              setPollError(null);

              if (
                typeof
                  job?.progress_percent ===
                'number'
              ) {
                setProgressPercent(
                  Math.max(
                    0,
                    Math.min(
                      100,
                      job.progress_percent
                    )
                  )
                );
              }
            }
          } catch (error) {
            if (
              generation !==
              generationRef.current
            ) {
              return {
                status: 'superseded',
                result: null,
              };
            }

            // Poll failure is not cancellation.
            // Keep polling the same authoritative job.
            if (mountedRef.current) {
              setPollError(error);
            }

            await wait(
              POLL_INTERVAL_MS
            );
            continue;
          }

          if (
            job.status === 'completed'
          ) {
            publishTerminalState(
              generation,
              100
            );

            return {
              status: 'completed',
              result:
                job.result ?? null,
            };
          }

          if (job.status === 'failed') {
            publishTerminalState(
              generation,
              100
            );

            if (
              isCancelledJob(job)
            ) {
              return {
                status: 'cancelled',
                result:
                  job.result ?? null,
              };
            }

            if (
              isQuotaExceededJob(job)
            ) {
              return {
                status:
                  'quota_exceeded',
                result:
                  job.result ?? null,
              };
            }

            return {
              status: 'failed',
              result:
                job.result ?? null,
              error:
                job.error ?? null,
            };
          }

          await wait(
            POLL_INTERVAL_MS
          );
        }

        return {
          status: 'superseded',
          result: null,
        };
      } catch (error) {
        resolveJobReady(null);

        if (
          generation ===
          generationRef.current
        ) {
          activeJobIdRef.current =
            null;
          jobReadyRef.current = null;
          publishProcessingState(false);

          if (mountedRef.current) {
            setPollError(error);
          }
        }

        throw error;
      }
    },
    [
      publishProcessingState,
      publishTerminalState,
    ]
  );

  const cancelAIJob =
    useCallback(async () => {
      if (!processingRef.current) {
        return {
          status: 'not_running',
          result: null,
        };
      }

      if (cancelPromiseRef.current) {
        return cancelPromiseRef.current;
      }

      const generation =
        generationRef.current;

      const cancellation =
        (async () => {
          if (mountedRef.current) {
            setIsCancelling(true);
          }

          let jobId =
            activeJobIdRef.current;

          if (
            !jobId &&
            jobReadyRef.current
          ) {
            jobId =
              await jobReadyRef.current;
          }

          if (!jobId) {
            throw new Error(
              'AI job identity is not available yet.'
            );
          }

          const stopLocalProcessing =
            () => {
              if (
                generation !==
                generationRef.current
              ) {
                return;
              }

              // Local processing ends only after
              // authoritative terminal proof.
              generationRef.current += 1;
              activeJobIdRef.current =
                null;
              jobReadyRef.current = null;
              publishProcessingState(
                false
              );

              if (mountedRef.current) {
                setProgressPercent(100);
                setPollError(null);
              }
            };

          try {
            await cancelProcessingJob(
              jobId
            );

            stopLocalProcessing();

            return {
              status: 'cancelled',
              result: null,
            };
          } catch (error) {
            let authoritativeJob =
              null;

            try {
              authoritativeJob =
                await getProcessingJob(
                  jobId
                );
            } catch {
              authoritativeJob =
                null;
            }

            if (
              authoritativeJob?.status ===
              'completed'
            ) {
              stopLocalProcessing();

              return {
                status: 'completed',
                result:
                  authoritativeJob
                    .result ?? null,
              };
            }

            if (
              authoritativeJob?.status ===
              'failed'
            ) {
              stopLocalProcessing();

              if (
                isCancelledJob(
                  authoritativeJob
                )
              ) {
                return {
                  status:
                    'cancelled',
                  result:
                    authoritativeJob
                      .result ?? null,
                };
              }

              if (
                isQuotaExceededJob(
                  authoritativeJob
                )
              ) {
                return {
                  status:
                    'quota_exceeded',
                  result:
                    authoritativeJob
                      .result ?? null,
                };
              }

              return {
                status: 'failed',
                result:
                  authoritativeJob
                    .result ?? null,
                error:
                  authoritativeJob
                    .error ?? null,
              };
            }

            // Cancellation failure with no terminal
            // server proof must leave the same job active.
            // Never navigate as if cancellation succeeded.
            if (
              error instanceof
                ApiError &&
              error.status === 409
            ) {
              throw error;
            }

            throw error;
          } finally {
            if (mountedRef.current) {
              setIsCancelling(false);
            }
          }
        })();

      cancelPromiseRef.current =
        cancellation;

      try {
        return await cancellation;
      } finally {
        cancelPromiseRef.current =
          null;
      }
    }, [publishProcessingState]);

  return {
    isProcessing,
    isCancelling,
    progressPercent,
    pollError,
    runAIJob,
    cancelAIJob,
  };
}

export default useCancellableAIJob;
