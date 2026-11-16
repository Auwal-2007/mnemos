import { Badge } from '../ui/Badge';
import { Icon } from '../ui/Icon';
import type { Answer, Citation, Claim } from '../../lib/api/types';
import './AnswerView.css';

export interface AnswerViewProps {
  answer: Answer;
  /** Opens the provenance inspector for the citation's chunk. */
  onInspectEvidence: (citation: Citation) => void;
  /** Per-claim verification, when the answer has been verified. */
  verificationById?: Record<string, { support: string; note: string | null }>;
}

const SUPPORT_TONE: Record<string, 'success' | 'warning' | 'danger' | 'neutral'> = {
  supported: 'success',
  partially_supported: 'warning',
  unsupported: 'danger',
  contradicted: 'danger',
  unverified: 'neutral',
};

const SUPPORT_LABEL: Record<string, string> = {
  supported: 'Supported',
  partially_supported: 'Partly supported',
  unsupported: 'Not supported',
  contradicted: 'Contradicted',
  unverified: 'Unverified',
};

function locator(citation: Citation): string {
  if (citation.page !== null) return `p. ${citation.page}`;
  if (citation.start_offset !== null) return `chars ${citation.start_offset}–${citation.end_offset ?? '?'}`;
  return `v${citation.version_number}`;
}

/**
 * Renders a grounded answer exactly as the backend reported it.
 *
 * Three states are treated as genuinely different, because they are:
 *
 *  * `answered` — claims, each with the citations backing it.
 *  * `abstained` — the system declined and said why. Rendered as a result, not
 *    as an error, since refusing without evidence is the designed behaviour.
 *  * `degraded` — an answer was produced but something was missing (for example
 *    no embedding provider, or a failed verification). The reason is shown
 *    rather than hidden, so the answer is never presented as stronger than it is.
 *
 * Citations are buttons, not decoration: each one resolves to the provenance
 * record for that exact chunk, which is what makes the answer checkable.
 */
export function AnswerView({
  answer,
  onInspectEvidence,
  verificationById = {},
}: AnswerViewProps): JSX.Element {
  const abstained = answer.status === 'abstained';
  const degraded = Boolean(answer.degraded_reason);

  return (
    <div className="answer">
      {(abstained || degraded) && (
        <div
          className={`answer__notice ${abstained ? 'answer__notice--abstain' : 'answer__notice--degraded'}`}
          role="status"
        >
          <Badge tone={abstained ? 'warning' : 'neutral'} variant="outline">
            {abstained ? 'No answer given' : 'Degraded'}
          </Badge>
          <p className="answer__notice-text">
            {abstained
              ? (answer.abstention_reason ??
                'The indexed knowledge does not contain enough evidence to answer this.')
              : answer.degraded_reason}
          </p>
        </div>
      )}

      {!abstained && answer.content && <p className="answer__content">{answer.content}</p>}

      {answer.claims.length > 0 && (
        <ol className="answer__claims">
          {answer.claims.map((claim, index) => (
            <ClaimRow
              key={`${index}-${claim.text.slice(0, 24)}`}
              claim={claim}
              index={index}
              onInspectEvidence={onInspectEvidence}
              verification={verificationById[claim.text]}
            />
          ))}
        </ol>
      )}

      {answer.claims.length === 0 && !abstained && answer.evidence.length > 0 && (
        <ul className="answer__citations" aria-label="Cited evidence">
          {answer.evidence.map((citation) => (
            <li key={citation.provenance_id}>
              <CitationChip citation={citation} onInspect={onInspectEvidence} />
            </li>
          ))}
        </ul>
      )}

      <p className="answer__counts">
        {answer.evidence_considered} passage{answer.evidence_considered === 1 ? '' : 's'} considered
        {answer.evidence_cited > 0 ? `, ${answer.evidence_cited} cited` : ', none cited'}
        {answer.execution?.model_id ? ` · ${answer.execution.model_id}` : ''}
        {answer.execution?.latency_ms != null ? ` · ${answer.execution.latency_ms} ms` : ''}
      </p>
    </div>
  );
}

function ClaimRow({
  claim,
  index,
  onInspectEvidence,
  verification,
}: {
  claim: Claim;
  index: number;
  onInspectEvidence: (citation: Citation) => void;
  verification?: { support: string; note: string | null };
}): JSX.Element {
  const support = verification?.support;
  return (
    <li className="answer__claim">
      <span className="answer__claim-index" aria-hidden="true">
        {index + 1}
      </span>
      <div className="answer__claim-body">
        <p className="answer__claim-text">{claim.text}</p>
        <div className="answer__claim-meta">
          {support && (
            <Badge tone={SUPPORT_TONE[support] ?? 'neutral'} variant="outline">
              {SUPPORT_LABEL[support] ?? support}
            </Badge>
          )}
          <ul className="answer__citations" aria-label="Evidence for this claim">
            {claim.citations.map((citation) => (
              <li key={citation.provenance_id}>
                <CitationChip citation={citation} onInspect={onInspectEvidence} />
              </li>
            ))}
          </ul>
        </div>
        {verification?.note && <p className="answer__claim-note">{verification.note}</p>}
      </div>
    </li>
  );
}

function CitationChip({
  citation,
  onInspect,
}: {
  citation: Citation;
  onInspect: (citation: Citation) => void;
}): JSX.Element {
  const superseded = citation.information_status === 'superseded';
  return (
    <button
      type="button"
      className={`citation ${superseded ? 'citation--superseded' : ''}`}
      onClick={() => onInspect(citation)}
      title={`${citation.source_title} — ${locator(citation)}`}
    >
      <Icon name="citation" size={12} />
      <span className="citation__title">{citation.source_title}</span>
      <span className="citation__locator">
        {locator(citation)}
        {superseded ? ' · superseded' : ''}
      </span>
    </button>
  );
}
