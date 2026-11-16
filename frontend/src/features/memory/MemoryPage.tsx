import { useCallback, useEffect, useState } from 'react';
import { PageContainer } from '../../components/layout/PageContainer';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { Icon } from '../../components/ui/Icon';
import { useAuth } from '../../lib/auth';
import { useMemory } from '../../lib/api/useMemory';
import { useWorkspaces } from '../../lib/api/useWorkspaces';
import type { Conflict, Correction } from '../../lib/api/types';
import './MemoryPage.css';

const CORRECTION_TONE: Record<string, 'warning' | 'success' | 'danger' | 'neutral'> = {
  proposed: 'warning',
  approved: 'success',
  rejected: 'danger',
  applied: 'success',
};

/**
 * Memory workspace: what the system believes, where it came from, what changed.
 *
 * The interface is built around one rule: a correction never overwrites history.
 * A proposed correction is shown beside the record it concerns, review and apply
 * are separate steps, and the applied result is a new revision linked to the old
 * one. Presenting this as a single "edit" button would misrepresent the model
 * and hide exactly the behaviour the product is claiming.
 */
export function MemoryPage(): JSX.Element {
  const { accessToken } = useAuth();
  const workspaces = useWorkspaces();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const memory = useMemory(workspaceId);

  const [provenanceId, setProvenanceId] = useState('');
  const [correctedText, setCorrectedText] = useState('');
  const [rationale, setRationale] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId && workspaces.data && workspaces.data.length > 0) {
      setWorkspaceId(workspaces.data[0].id);
    }
  }, [workspaceId, workspaces.data]);

  const submitCorrection = useCallback(async () => {
    if (!provenanceId.trim() || !correctedText.trim()) return;
    const ok = await memory.propose({
      provenanceId: provenanceId.trim(),
      correctedText: correctedText.trim(),
      rationale: rationale.trim() || undefined,
    });
    if (ok) {
      setProvenanceId('');
      setCorrectedText('');
      setRationale('');
      setFormOpen(false);
      setNotice('Correction proposed. It needs review before it changes anything.');
    }
  }, [memory, provenanceId, correctedText, rationale]);

  const canUse = Boolean(workspaceId && accessToken);
  const openConflicts = memory.conflicts.filter((conflict) => conflict.status === 'open');

  return (
    <PageContainer width="default">
      <div className="memory">
        <header className="memory__header">
          <p className="eyebrow">Memory</p>
          <h1 className="memory__title display">What MNEMOS believes</h1>
          <p className="memory__lede">
            Corrections do not overwrite what was there before. A proposal is reviewed, then
            applied as a new revision that links back to the original, so the history stays
            readable and answers can cite the version they were built from.
          </p>
        </header>

        {workspaces.data && workspaces.data.length > 1 && (
          <div className="memory__workspace">
            <label htmlFor="memory-workspace">Workspace</label>
            <select
              id="memory-workspace"
              value={workspaceId ?? ''}
              onChange={(event) => setWorkspaceId(event.target.value || null)}
            >
              {workspaces.data.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {notice && (
          <p className="memory__notice" role="status">
            {notice}
          </p>
        )}

        {memory.error && (
          <p className="memory__error" role="alert">
            {memory.error}
          </p>
        )}

        {!canUse && !workspaces.isLoading && (
          <EmptyState
            icon={<Icon name="memory" size={20} />}
            title="Sign in to view memory"
            description="Corrections and conflicts belong to a workspace, and workspaces require a session."
          />
        )}

        {canUse && (
          <>
            <section className="memory__section" aria-labelledby="corrections-heading">
              <div className="memory__section-head">
                <h2 id="corrections-heading">Corrections</h2>
                <div className="memory__actions">
                  <Button
                    variant="secondary"
                    onClick={() => setFormOpen((open) => !open)}
                    disabled={memory.isMutating}
                  >
                    {formOpen ? 'Cancel' : 'Propose correction'}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={memory.reload}
                    disabled={memory.isLoading}
                    aria-label="Reload memory"
                  >
                    <Icon name="refresh" size={16} />
                  </Button>
                </div>
              </div>

              {formOpen && (
                <form
                  className="memory__form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void submitCorrection();
                  }}
                >
                  <label htmlFor="correction-provenance">Provenance id of the passage</label>
                  <input
                    id="correction-provenance"
                    value={provenanceId}
                    onChange={(event) => setProvenanceId(event.target.value)}
                    placeholder="Open a citation in a conversation to copy its provenance id"
                    required
                  />
                  <label htmlFor="correction-text">What should it say instead?</label>
                  <textarea
                    id="correction-text"
                    value={correctedText}
                    onChange={(event) => setCorrectedText(event.target.value)}
                    rows={3}
                    required
                  />
                  <label htmlFor="correction-rationale">Why? (optional)</label>
                  <input
                    id="correction-rationale"
                    value={rationale}
                    onChange={(event) => setRationale(event.target.value)}
                  />
                  <Button type="submit" disabled={memory.isMutating}>
                    {memory.isMutating ? 'Proposing…' : 'Propose'}
                  </Button>
                </form>
              )}

              {memory.corrections.length === 0 && !memory.isLoading ? (
                <EmptyState
                  icon={<Icon name="history" size={20} />}
                  title="No corrections yet"
                  description="When you disagree with something MNEMOS believes, propose a correction and it will be reviewed before anything changes."
                />
              ) : (
                <ul className="memory__list">
                  {memory.corrections.map((correction) => (
                    <CorrectionRow
                      key={correction.id}
                      correction={correction}
                      busy={memory.isMutating}
                      onReview={memory.review}
                      onApply={memory.apply}
                    />
                  ))}
                </ul>
              )}
            </section>

            <section className="memory__section" aria-labelledby="conflicts-heading">
              <div className="memory__section-head">
                <h2 id="conflicts-heading">Conflicts</h2>
                <Button
                  variant="secondary"
                  onClick={() => void memory.detect()}
                  disabled={memory.isMutating}
                >
                  Detect conflicts
                </Button>
              </div>

              {openConflicts.length === 0 && !memory.isLoading ? (
                <EmptyState
                  icon={<Icon name="alert" size={20} />}
                  title="No open conflicts"
                  description="A conflict is recorded when two sources disagree in a way that matters. Running detection compares indexed passages against each other."
                />
              ) : (
                <ul className="memory__list">
                  {memory.conflicts.map((conflict) => (
                    <ConflictRow
                      key={conflict.id}
                      conflict={conflict}
                      busy={memory.isMutating}
                      onResolve={memory.resolve}
                    />
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </PageContainer>
  );
}

function CorrectionRow({
  correction,
  busy,
  onReview,
  onApply,
}: {
  correction: Correction;
  busy: boolean;
  onReview: (id: string, approve: boolean, note?: string) => Promise<boolean>;
  onApply: (id: string) => Promise<boolean>;
}): JSX.Element {
  return (
    <li className="memory__item">
      <div className="memory__item-head">
        <Badge tone={CORRECTION_TONE[correction.status] ?? 'neutral'} variant="outline">
          {correction.status}
        </Badge>
        {correction.is_self_review && (
          <Badge tone="warning" variant="outline" title="Reviewing your own correction is blocked">
            Self-review
          </Badge>
        )}
      </div>
      <p className="memory__item-text">{correction.corrected_text}</p>
      {correction.rationale && <p className="memory__item-note">{correction.rationale}</p>}
      {correction.applied_provenance_id && (
        <p className="memory__item-note">
          Applied as revision <code>{correction.applied_provenance_id.slice(0, 8)}</code> — the
          original record still exists and is linked.
        </p>
      )}
      <div className="memory__item-actions">
        {correction.status === 'proposed' && (
          <>
            <Button variant="secondary" disabled={busy} onClick={() => void onReview(correction.id, true)}>
              Approve
            </Button>
            <Button variant="ghost" disabled={busy} onClick={() => void onReview(correction.id, false)}>
              Reject
            </Button>
          </>
        )}
        {correction.status === 'approved' && (
          <Button disabled={busy} onClick={() => void onApply(correction.id)}>
            Apply as revision
          </Button>
        )}
      </div>
    </li>
  );
}

function ConflictRow({
  conflict,
  busy,
  onResolve,
}: {
  conflict: Conflict;
  busy: boolean;
  onResolve: (id: string, dismiss: boolean, note?: string) => Promise<boolean>;
}): JSX.Element {
  return (
    <li className="memory__item">
      <div className="memory__item-head">
        <Badge tone={conflict.status === 'open' ? 'warning' : 'neutral'} variant="outline">
          {conflict.status}
        </Badge>
        <span className="memory__item-meta">{conflict.detection_method}</span>
      </div>
      <p className="memory__item-text">{conflict.detected_reason}</p>
      <p className="memory__item-note">
        Between <code>{conflict.provenance_a.slice(0, 8)}</code> and{' '}
        <code>{conflict.provenance_b.slice(0, 8)}</code>
        {conflict.score !== null ? ` · score ${conflict.score.toFixed(2)}` : ''}
      </p>
      {conflict.resolution_note && (
        <p className="memory__item-note">{conflict.resolution_note}</p>
      )}
      {conflict.status === 'open' && (
        <div className="memory__item-actions">
          <Button variant="secondary" disabled={busy} onClick={() => void onResolve(conflict.id, false)}>
            Mark resolved
          </Button>
          <Button variant="ghost" disabled={busy} onClick={() => void onResolve(conflict.id, true)}>
            Dismiss
          </Button>
        </div>
      )}
    </li>
  );
}
