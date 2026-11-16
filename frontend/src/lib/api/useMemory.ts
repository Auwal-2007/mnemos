/**
 * Memory state hooks: corrections and conflicts.
 *
 * Both follow the same contract as `useSources` — load, expose an error, allow a
 * reload — and neither fabricates an entry when the list is empty.
 *
 * The mutation helpers deliberately re-fetch after success rather than patching
 * local state. Corrections move through propose → review → apply and may be
 * rejected by the server (self-review is blocked by a trigger), so the only
 * truthful view after a mutation is the one the server returns.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth';
import { toErrorMessage } from './client';
import {
  applyCorrection,
  detectConflicts,
  fetchConflicts,
  fetchCorrections,
  proposeCorrection,
  resolveConflict,
  reviewCorrection,
  type ProposeCorrectionInput,
} from './memory';
import type { Conflict, Correction } from './types';

export interface MemoryState {
  corrections: Correction[];
  conflicts: Conflict[];
  error: string | null;
  isLoading: boolean;
  /** True while a mutation is in flight. */
  isMutating: boolean;
  reload: () => void;
  propose: (input: ProposeCorrectionInput) => Promise<boolean>;
  review: (correctionId: string, approve: boolean, note?: string) => Promise<boolean>;
  apply: (correctionId: string) => Promise<boolean>;
  detect: () => Promise<number | null>;
  resolve: (conflictId: string, dismiss: boolean, note?: string) => Promise<boolean>;
}

export function useMemory(workspaceId: string | null): MemoryState {
  const { accessToken } = useAuth();
  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(workspaceId && accessToken));
  const [isMutating, setIsMutating] = useState(false);
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
      setCorrections([]);
      setConflicts([]);
      setIsLoading(false);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setIsLoading(true);
    setError(null);

    Promise.all([
      fetchCorrections(accessToken, workspaceId, controller.signal),
      fetchConflicts(accessToken, workspaceId, controller.signal),
    ])
      .then(([correctionList, conflictList]) => {
        if (!mounted.current || controller.signal.aborted) return;
        setCorrections(correctionList.items);
        setConflicts(conflictList.items);
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

  /** Run a mutation, surface its error, and reload on success. */
  const mutate = useCallback(
    async <T,>(action: (token: string, workspace: string) => Promise<T>): Promise<T | null> => {
      if (!accessToken || !workspaceId) return null;
      setIsMutating(true);
      setError(null);
      try {
        const result = await action(accessToken, workspaceId);
        reload();
        return result;
      } catch (cause) {
        setError(toErrorMessage(cause));
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    [accessToken, workspaceId, reload],
  );

  const propose = useCallback(
    async (input: ProposeCorrectionInput) =>
      (await mutate((token, workspace) => proposeCorrection(token, workspace, input))) !== null,
    [mutate],
  );

  const review = useCallback(
    async (correctionId: string, approve: boolean, note?: string) =>
      (await mutate((token) => reviewCorrection(token, correctionId, approve, note))) !== null,
    [mutate],
  );

  const apply = useCallback(
    async (correctionId: string) =>
      (await mutate((token) => applyCorrection(token, correctionId))) !== null,
    [mutate],
  );

  const detect = useCallback(
    async () => {
      const result = await mutate((token, workspace) => detectConflicts(token, workspace));
      return result ? result.recorded_ids.length : null;
    },
    [mutate],
  );

  const resolve = useCallback(
    async (conflictId: string, dismiss: boolean, note?: string) =>
      (await mutate((token) => resolveConflict(token, conflictId, dismiss, note))) !== null,
    [mutate],
  );

  return {
    corrections,
    conflicts,
    error,
    isLoading,
    isMutating,
    reload,
    propose,
    review,
    apply,
    detect,
    resolve,
  };
}
