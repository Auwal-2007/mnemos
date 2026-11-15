import { useRef, useState, type DragEvent, type FormEvent } from 'react';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { ApiError, toErrorMessage } from '../../lib/api/client';
import {
  SUPPORTED_EXTENSIONS,
  UPLOAD_MAX_BYTES,
  createNote,
  formatBytes,
  uploadDocument,
} from '../../lib/api/knowledge';
import type { IngestionResult } from '../../lib/api/types';
import './SourceSubmitPanel.css';

type Mode = 'document' | 'note';

export interface SourceSubmitPanelProps {
  workspaceId: string | null;
  accessToken: string | null;
  onSubmitted: (result: IngestionResult) => void;
  onSourceUpdated: (sourceId: string) => void;
}

/** Stable idempotency key so a retried submission cannot duplicate a source. */
function makeIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `ingest-${crypto.randomUUID()}`;
  }
  return `ingest-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function describeFailure(error: unknown): string {
  if (error instanceof ApiError) {
    const reason = (error.details as { reason?: string } | undefined)?.reason;
    if (reason === 'type_mismatch') {
      return 'The file contents do not match its extension. Check that the file is what it claims to be.';
    }
    if (reason === 'unsupported_encoding') {
      return 'The file is not UTF-8 text. Re-save it as UTF-8 and try again.';
    }
    if (reason === 'binary_content') {
      return 'That file looks like binary data, not readable text.';
    }
    return error.message;
  }
  return toErrorMessage(error);
}

/**
 * Upload a document or write a note.
 *
 * Both paths create a versioned source on the server; the panel never reports
 * success it did not receive. When extraction fails the source is still
 * created, and the panel says so explicitly instead of hiding it.
 */
export function SourceSubmitPanel({
  workspaceId,
  accessToken,
  onSubmitted,
  onSourceUpdated,
}: SourceSubmitPanelProps): JSX.Element {
  const [mode, setMode] = useState<Mode>('document');
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [noteTitle, setNoteTitle] = useState('');
  const [noteBody, setNoteBody] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const disabled = !workspaceId || !accessToken || isSubmitting;

  function chooseFile(next: File | null): void {
    setError(null);
    setNotice(null);
    if (!next) {
      setFile(null);
      return;
    }
    const lower = next.name.toLowerCase();
    const extensionOk = SUPPORTED_EXTENSIONS.some((extension) => lower.endsWith(extension));
    if (!extensionOk) {
      setFile(null);
      setError('Only PDF, Markdown (.md) and plain text (.txt) files are supported.');
      return;
    }
    if (next.size > UPLOAD_MAX_BYTES) {
      setFile(null);
      setError(`That file is ${formatBytes(next.size)}. The limit is ${formatBytes(UPLOAD_MAX_BYTES)}.`);
      return;
    }
    if (next.size === 0) {
      setFile(null);
      setError('That file is empty.');
      return;
    }
    setFile(next);
    if (!title) setTitle(next.name.replace(/\.[^.]+$/, ''));
  }

  function handleDrop(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setIsDragging(false);
    if (disabled) return;
    chooseFile(event.dataTransfer.files[0] ?? null);
  }

  async function submitDocument(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!file || !accessToken || !workspaceId) return;
    setIsSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const result = await uploadDocument(accessToken, workspaceId, file, {
        title: title.trim() || undefined,
        idempotencyKey: makeIdempotencyKey(),
      });
      onSubmitted(result);
      onSourceUpdated(result.source.id);
      setFile(null);
      setTitle('');
      if (inputRef.current) inputRef.current.value = '';
      setNotice(
        result.extraction.status === 'failed'
          ? `Stored "${result.source.title}", but text extraction failed: ${
              result.extraction.error_message ?? 'unknown reason'
            }.`
          : `Stored "${result.source.title}" — ${result.extraction.char_count.toLocaleString()} characters extracted.`,
      );
    } catch (cause) {
      setError(describeFailure(cause));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function submitNote(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!accessToken || !workspaceId) return;
    setIsSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const result = await createNote(accessToken, workspaceId, {
        title: noteTitle.trim(),
        content: noteBody,
        idempotency_key: makeIdempotencyKey(),
      });
      onSubmitted(result);
      onSourceUpdated(result.source.id);
      setNoteTitle('');
      setNoteBody('');
      setNotice(`Saved "${result.source.title}" as a versioned note.`);
    } catch (cause) {
      setError(describeFailure(cause));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section className="submit" aria-labelledby="submit-heading">
      <div className="submit__head">
        <h2 className="submit__title" id="submit-heading">
          Add to your corpus
        </h2>
        <div className="submit__modes" role="tablist" aria-label="Submission type">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'document'}
            className="submit__mode"
            onClick={() => setMode('document')}
            disabled={isSubmitting}
          >
            <Icon name="document" size={14} /> Upload a file
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'note'}
            className="submit__mode"
            onClick={() => setMode('note')}
            disabled={isSubmitting}
          >
            <Icon name="note" size={14} /> Write a note
          </button>
        </div>
      </div>

      {!workspaceId && (
        <p className="submit__blocked" role="status">
          Create or join a workspace before adding sources.
        </p>
      )}

      {mode === 'document' ? (
        <form className="submit__form" onSubmit={(event) => void submitDocument(event)}>
          <div
            className={`submit__drop ${isDragging ? 'submit__drop--active' : ''}`}
            onDragOver={(event) => {
              event.preventDefault();
              if (!disabled) setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
          >
            <input
              ref={inputRef}
              id="source-file"
              type="file"
              className="submit__file-input"
              accept=".pdf,.md,.markdown,.txt,application/pdf,text/plain,text/markdown"
              onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
              disabled={disabled}
            />
            <label htmlFor="source-file" className="submit__drop-label">
              <Icon name="document" size={20} />
              <span className="submit__drop-title">
                {file ? file.name : 'Choose a file or drag it here'}
              </span>
              <span className="submit__drop-hint">
                {file
                  ? `${formatBytes(file.size)} ready to upload`
                  : 'PDF, Markdown or plain text · up to 50 MB'}
              </span>
            </label>
          </div>

          <div className="submit__row">
            <label className="submit__label" htmlFor="source-title">
              Title <span className="submit__optional">(optional)</span>
            </label>
            <input
              id="source-title"
              type="text"
              className="submit__input"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              maxLength={300}
              placeholder="Defaults to the file name"
              disabled={disabled}
            />
          </div>

          <div className="submit__actions">
            <Button
              type="submit"
              variant="primary"
              loading={isSubmitting}
              disabled={disabled || !file}
            >
              Upload and extract
            </Button>
            <p className="submit__note">
              The original file is stored privately and never modified. Text is
              extracted into a separate record.
            </p>
          </div>
        </form>
      ) : (
        <form className="submit__form" onSubmit={(event) => void submitNote(event)}>
          <div className="submit__row">
            <label className="submit__label" htmlFor="note-title">
              Title
            </label>
            <input
              id="note-title"
              type="text"
              className="submit__input"
              value={noteTitle}
              onChange={(event) => setNoteTitle(event.target.value)}
              maxLength={300}
              required
              placeholder="What is this note about?"
              disabled={disabled}
            />
          </div>
          <div className="submit__row">
            <label className="submit__label" htmlFor="note-body">
              Note
            </label>
            <textarea
              id="note-body"
              className="submit__textarea"
              value={noteBody}
              onChange={(event) => setNoteBody(event.target.value)}
              rows={7}
              required
              maxLength={200_000}
              placeholder="Write the note. It becomes a versioned source, so later edits create a new version rather than overwriting this one."
              disabled={disabled}
            />
            <span className="submit__counter">{noteBody.length.toLocaleString()} / 200,000</span>
          </div>
          <div className="submit__actions">
            <Button
              type="submit"
              variant="primary"
              loading={isSubmitting}
              disabled={disabled || !noteBody.trim() || !noteTitle.trim()}
            >
              Save note
            </Button>
          </div>
        </form>
      )}

      {error && (
        <p className="submit__feedback submit__feedback--error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="submit__feedback submit__feedback--ok" role="status">
          {notice}
        </p>
      )}
    </section>
  );
}
