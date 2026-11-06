'use client';

import { useSyncExternalStore } from 'react';

const query = '(prefers-reduced-motion: reduce)';
function subscribe(listener: () => void) {
  const media = window.matchMedia(query);
  media.addEventListener('change', listener);
  return () => media.removeEventListener('change', listener);
}
export function useReducedMotion() {
  // Do not start animation until browser preferences are available.
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches, () => true);
}
