import type { BadgeProps } from '../../components/ui/Badge';
import type { ProcessingStatus } from '../../lib/api/types';

type Tone = NonNullable<BadgeProps['tone']>;

export interface StatusPresentation {
  label: string;
  tone: Tone;
  /** Plain-language explanation shown on hover and to screen readers. */
  description: string;
  /** True while the pipeline is still working on this source. */
  busy: boolean;
}

/**
 * Single source of truth for how a processing status is presented.
 *
 * Every value the backend can return is mapped. An unknown value falls back to
 * a neutral, honest label rather than being rendered as if it were successful.
 */
const STATUS: Record<ProcessingStatus, StatusPresentation> = {
  pending: {
    label: 'Queued',
    tone: 'neutral',
    description: 'Stored and waiting to be processed.',
    busy: true,
  },
  validating: {
    label: 'Validating',
    tone: 'accent',
    description: 'Checking the file type, size and encoding.',
    busy: true,
  },
  extracting: {
    label: 'Extracting text',
    tone: 'accent',
    description: 'Reading the text and page structure from the original.',
    busy: true,
  },
  extracted: {
    label: 'Text extracted',
    tone: 'accent',
    description: 'Text extracted. Chunking has not run yet, so it is not searchable.',
    busy: true,
  },
  chunking: {
    label: 'Chunking',
    tone: 'accent',
    description: 'Splitting the text into citable passages.',
    busy: true,
  },
  indexing: {
    label: 'Indexing',
    tone: 'accent',
    description: 'Generating embeddings for retrieval.',
    busy: true,
  },
  ready: {
    label: 'Ready',
    tone: 'success',
    description: 'Processed and searchable.',
    busy: false,
  },
  failed: {
    label: 'Failed',
    tone: 'danger',
    description: 'Processing failed. Open the source for the reason.',
    busy: false,
  },
};

export function presentStatus(status: string): StatusPresentation {
  return (
    STATUS[status as ProcessingStatus] ?? {
      label: status || 'Unknown',
      tone: 'neutral',
      description: 'This status is not recognised by the interface.',
      busy: false,
    }
  );
}

/** True when the source is stored but not yet searchable. */
export function isSearchable(status: string): boolean {
  return status === 'ready';
}
