import { useCallback, useEffect, useRef, useState } from 'react';
import { toErrorMessage } from '../api/client';

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  isLoading: boolean;
  reload: () => void;
}

/**
 * Run an async loader with consistent loading/error semantics.
 * The loader must be stable (wrap in useCallback) or omitted.
 */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    loader()
      .then((result) => {
        if (!cancelled && mounted.current) setData(result);
      })
      .catch((cause: unknown) => {
        if (!cancelled && mounted.current) setError(toErrorMessage(cause));
      })
      .finally(() => {
        if (!cancelled && mounted.current) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  return { data, error, isLoading, reload };
}
