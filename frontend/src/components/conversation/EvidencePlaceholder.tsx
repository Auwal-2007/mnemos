import type { EvidenceRef } from './types';
import './EvidencePlaceholder.css';

/**
 * Evidence display. Renders real references when present; when retrieval
 * has no verified citations, callers pass none and this renders nothing. Verified
 * citation rendering lives in AnswerView, which opens real provenance records.
 */
export function EvidencePlaceholder({ evidence }: { evidence: EvidenceRef[] }): JSX.Element {
  return (
    <div className="evidence">
      <p className="evidence__label">Sources</p>
      <ul className="evidence__list" role="list">
        {evidence.map((item) => (
          <li key={item.id} className="evidence__item">
            <span className="evidence__title">{item.sourceTitle}</span>
            {item.locator && <span className="evidence__locator">{item.locator}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
