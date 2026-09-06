import { useEffect, useRef, useState } from 'react';

export function useSmoothAIProgress(
  active,
  initialPercent = 8,
  capPercent = 94,
  timeConstantMs = 18000
) {
  const [progress, setProgress] = useState(0);
  const startedAtRef = useRef(0);

  useEffect(() => {
    if (!active) {
      startedAtRef.current = 0;
      setProgress(0);
      return undefined;
    }

    startedAtRef.current = Date.now();
    setProgress(initialPercent);

    const updateProgress = () => {
      const elapsedMs =
        Date.now() - startedAtRef.current;

      const eased =
        1 -
        Math.exp(
          -elapsedMs /
            Math.max(timeConstantMs, 1)
        );

      const nextProgress = Math.min(
        capPercent,
        Math.round(
          initialPercent +
            (
              capPercent -
              initialPercent
            ) *
              eased
        )
      );

      setProgress((current) =>
        Math.max(
          current,
          nextProgress
        )
      );
    };

    const timer = setInterval(
      updateProgress,
      500
    );

    updateProgress();

    return () => {
      clearInterval(timer);
    };
  }, [
    active,
    initialPercent,
    capPercent,
    timeConstantMs,
  ]);

  return progress;
}

export default useSmoothAIProgress;
