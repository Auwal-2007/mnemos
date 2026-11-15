import { PageContainer } from '../../components/layout/PageContainer';
import { PageHeader } from '../../components/layout/PageHeader';
import { Badge } from '../../components/ui/Badge';
import { Icon } from '../../components/ui/Icon';
import './KnowledgePage.css';

const sections = [
  {
    id: 'documents',
    icon: 'document' as const,
    title: 'Documents',
    body: 'Uploaded files and imported sources, with their extraction status and checksum.',
  },
  {
    id: 'notes',
    icon: 'note' as const,
    title: 'Notes',
    body: 'First-class notes you write directly, versioned alongside imported material.',
  },
  {
    id: 'entries',
    icon: 'workspace' as const,
    title: 'Knowledge entries',
    body: 'Durable assertions with provenance, confidence and current/superseded state.',
  },
  {
    id: 'revisions',
    icon: 'history' as const,
    title: 'Revision history',
    body: 'Every change to an entry, including supersession and user corrections.',
  },
];

/**
 * Structural foundation for the knowledge workspace. No ingestion,
 * indexing or retrieval is implemented; actions are visibly unavailable.
 */
export function KnowledgePage(): JSX.Element {
  return (
    <PageContainer width="default">
      <PageHeader
        eyebrow="Knowledge workspace"
        title="Your corpus"
        description="Documents, notes and verified knowledge entries will live here. The layout and information architecture are in place; ingestion and retrieval are not."
        actions={<Badge tone="warning">Not yet populated</Badge>}
      />

      <div className="kb-search" role="search">
        <Icon name="search" size={16} />
        <input
          type="search"
          className="kb-search__input"
          placeholder="Search your knowledge…"
          aria-label="Search your knowledge"
          disabled
          title="Search becomes available once retrieval is implemented"
        />
        <span className="kb-search__hint">Available after retrieval is implemented</span>
      </div>

      <ul className="kb-sections" role="list">
        {sections.map((section) => (
          <li key={section.id}>
            <section className="kb-section" aria-labelledby={`kb-${section.id}`}>
              <div className="kb-section__head">
                <span className="kb-section__icon" aria-hidden="true">
                  <Icon name={section.icon} size={18} />
                </span>
                <h2 className="kb-section__title" id={`kb-${section.id}`}>
                  {section.title}
                </h2>
                <button
                  type="button"
                  className="kb-section__action"
                  disabled
                  title="Available in a later phase"
                >
                  <Icon name="plus" size={14} />
                  <span className="sr-only">Add to {section.title} — available later</span>
                </button>
              </div>
              <p className="kb-section__body">{section.body}</p>
              <p className="kb-section__empty">Empty — no {section.title.toLowerCase()} stored yet.</p>
            </section>
          </li>
        ))}
      </ul>

      <section className="kb-roadmap" aria-labelledby="kb-roadmap-heading">
        <h2 className="kb-roadmap__title" id="kb-roadmap-heading">
          What arrives later
        </h2>
        <ol className="kb-roadmap__list">
          <li>Document ingestion and text extraction</li>
          <li>Chunking and embedding generation</li>
          <li>Vector retrieval with source citations</li>
          <li>Revision, supersession and conflict handling</li>
        </ol>
      </section>
    </PageContainer>
  );
}
