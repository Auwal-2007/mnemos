import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth';
import { toErrorMessage } from './client';
import { fetchSources } from './knowledge';
import type { KnowledgeSource } from './types';

export interface SourcesState {
  sources: KnowledgeSource[];
  error: string | null;
  isLoading: boolean;
  /** True when there is no session to query with. */
  needsAuth: boolean;
  /** True when no workspace exists yet, so there is nothing to load. */
  needsWorkspace: boolean;
  reload: () => void;
  /** Insert or replace a source locally after a successful submission. */
  upsert: (source: KnowledgeSource) => void;
  remove: (sourceId: string) => void;
}

/**
 * Load the sources of one workspace.
 *
 * Deliberately does not invent a placeholder list: an empty corpus renders as
 * an empty state, and a failure renders as an error, never as sample data.
 */
export function useSources(workspaceId: string | null): SourcesState {
  const { accessToken } = useAuth();
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(workspaceId && accessToken));
  const [reloadToken, setReloadToken] = useState(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!workspaceId || !accessToken) {
      setSources([]);
      setIsLoading(false);
      setError(null);
      return;
    }

    const controller = new AbortController();
    setIsLoading(true);
    setError(null);

    fetchSources(accessToken, workspaceId, controller.signal)
      .then((rows) => {
        if (mounted.current && !controller.signal.aborted) setSources(rows);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (mounted.current) setError(toErrorMessage(cause));
      })
      .finally(() => {
        if (mounted.current && !controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [workspaceId, accessToken, reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  const upsert = useCallback((source: KnowledgeSource) => {
    setSources((current) => {
      const without = current.filter((item) => item.id !== source.id);
      return [source, ...without];
    });
  }, []);

  const remove = useCallback((sourceId: string) => {
    setSources((current) => current.filter((item) => item.id !== sourceId));
  }, []);

  return {
    sources,
    error,
    isLoading,
    needsAuth: !accessToken,
    needsWorkspace: Boolean(accessToken) && !workspaceId,
    reload,
    upsert,
    remove,
  };
}
