import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { KnowledgeSource } from '../../lib/api/types';

const authState = { accessToken: 'test-token', status: 'authenticated', isConfigured: true };
vi.mock('../../lib/auth', () => ({
  useAuth: () => authState,
}));

const WORKSPACE = {
  id: 'ws-1',
  owner_id: 'u-1',
  name: 'Personal',
  slug: 'personal',
  description: null,
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
};

function makeSource(overrides: Partial<KnowledgeSource> = {}): KnowledgeSource {
  return {
    id: 'src-1',
    workspace_id: 'ws-1',
    owner_id: 'u-1',
    kind: 'document',
    title: 'Report',
    original_filename: 'report.pdf',
    mime_type: 'application/pdf',
    size_bytes: 2048,
    content_hash: 'a'.repeat(64),
    processing_status: 'ready',
    processing_error_code: null,
    processing_error_detail: null,
    processing_attempts: 1,
    metadata: {},
    submitted_at: '2026-11-10T10:00:00Z',
    created_at: '2026-11-10T10:00:00Z',
    updated_at: '2026-11-10T10:00:00Z',
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('KnowledgePage', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  async function renderPage() {
    const { KnowledgePage } = await import('./KnowledgePage');
    return render(<KnowledgePage />);
  }

  it('shows an honest empty state when nothing has been submitted', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes('/workspaces/ws-1/sources')) return jsonResponse([]);
      if (url.endsWith('/workspaces')) return jsonResponse([WORKSPACE]);
      return jsonResponse({}, 404);
    });

    await renderPage();

    expect(await screen.findByText(/nothing submitted yet/i)).toBeTruthy();
    expect(await screen.findByText(/upload a pdf, markdown or text file above/i)).toBeTruthy();
    // No fabricated sample documents.
    expect(screen.queryByText('Report')).not.toBeInTheDocument();
  });

  it('lists real sources with their real status and size', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes('/workspaces/ws-1/sources')) {
        return jsonResponse([makeSource({ processing_status: 'extracted' })]);
      }
      if (url.endsWith('/workspaces')) return jsonResponse([WORKSPACE]);
      return jsonResponse({}, 404);
    });

    await renderPage();

    const list = await screen.findByRole('list', { name: /sources/i });
    expect(within(list).getByText('Report')).toBeInTheDocument();
    expect(within(list).getByText(/2\.0 kB/)).toBeInTheDocument();
    // "extracted" is presented truthfully as not-yet-searchable.
    expect(within(list).getByText('Text extracted')).toBeInTheDocument();
    expect(screen.getByText('0 searchable')).toBeInTheDocument();
  });

  it('shows the failure reason for a failed source', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes('/workspaces/ws-1/sources')) {
        return jsonResponse([
          makeSource({
            processing_status: 'failed',
            processing_error_code: 'no_text_layer',
            processing_error_detail: 'This PDF has no extractable text.',
          }),
        ]);
      }
      if (url.endsWith('/workspaces')) return jsonResponse([WORKSPACE]);
      return jsonResponse({}, 404);
    });

    await renderPage();

    expect(await screen.findByText(/1 failed/)).toBeInTheDocument();
    expect(screen.getByText(/no extractable text/i)).toBeInTheDocument();
  });

  it('uploads a file and reports the real character count', async () => {
    const uploaded = makeSource({ processing_status: 'extracted' });
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.includes('/sources/upload') && init?.method === 'POST') {
        return jsonResponse(
          {
            source: uploaded,
            version_id: 'ver-1',
            version_number: 1,
            extraction: {
              status: 'extracted',
              method: 'pdf',
              char_count: 1234,
              page_count: 3,
              segment_count: 3,
              error_code: null,
              error_message: null,
            },
            duplicate_of_existing: false,
          },
          201,
        );
      }
      if (url.includes('/knowledge/sources/src-1')) {
        return jsonResponse({ ...uploaded, versions: [], current_version: null });
      }
      if (url.includes('/workspaces/ws-1/sources')) return jsonResponse([]);
      if (url.endsWith('/workspaces')) return jsonResponse([WORKSPACE]);
      return jsonResponse({}, 404);
    });

    await renderPage();
    const user = userEvent.setup();

    const input = await screen.findByLabelText(/choose a file or drag it here/i, {
      selector: 'input',
    });
    const file = new File(['%PDF-1.7 test'], 'report.pdf', { type: 'application/pdf' });
    await user.upload(input as HTMLInputElement, file);

    await user.click(screen.getByRole('button', { name: /upload and extract/i }));

    expect(await screen.findByText(/1,234 characters extracted/i)).toBeInTheDocument();

    const uploadCall = fetchMock.mock.calls.find((call) =>
      String(call[0]).includes('/sources/upload'),
    );
    expect(uploadCall).toBeTruthy();
    const headers = (uploadCall?.[1] as RequestInit).headers as Record<string, string>;
    // The idempotency key makes a retried request non-duplicating.
    expect(headers['Idempotency-Key']).toMatch(/^ingest-/);
    expect(headers['Content-Type']).toBeUndefined();
  });

  it('does not report success when the server rejects the upload', async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.includes('/sources/upload') && init?.method === 'POST') {
        return jsonResponse(
          {
            error: {
              code: 'ingestion_rejected',
              message: 'The file contents do not match the declared file type.',
              request_id: 'req-1',
              details: { reason: 'type_mismatch' },
            },
          },
          422,
        );
      }
      if (url.includes('/workspaces/ws-1/sources')) return jsonResponse([]);
      if (url.endsWith('/workspaces')) return jsonResponse([WORKSPACE]);
      return jsonResponse({}, 404);
    });

    await renderPage();
    const user = userEvent.setup();

    const input = await screen.findByLabelText(/choose a file or drag it here/i, {
      selector: 'input',
    });
    await user.upload(
      input as HTMLInputElement,
      new File(['x'], 'fake.pdf', { type: 'application/pdf' }),
    );
    await user.click(screen.getByRole('button', { name: /upload and extract/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/contents do not match its extension/i);
    expect(screen.queryByText(/characters extracted/i)).not.toBeInTheDocument();
  });

  it('rejects an unsupported file before calling the server', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes('/workspaces/ws-1/sources')) return jsonResponse([]);
      if (url.endsWith('/workspaces')) return jsonResponse([WORKSPACE]);
      return jsonResponse({}, 404);
    });

    await renderPage();

    const input = await screen.findByLabelText(/choose a file or drag it here/i, {
      selector: 'input',
    });
    // Dispatching change directly mirrors a drag-and-drop, which bypasses the
    // `accept` attribute. The client-side guard must still reject the file.
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'image.png', { type: 'image/png' })] },
    });

    expect(await screen.findByText(/only pdf, markdown/i)).toBeTruthy();
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/upload'))).toBe(false);
  });

  it('creates a note and says it is versioned', async () => {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.includes('/sources/note') && init?.method === 'POST') {
        return jsonResponse(
          {
            source: makeSource({ id: 'note-1', kind: 'note', title: 'Idea', original_filename: null }),
            version_id: 'ver-1',
            version_number: 1,
            extraction: {
              status: 'extracted',
              method: 'plain-text',
              char_count: 42,
              page_count: 1,
              segment_count: 1,
              error_code: null,
              error_message: null,
            },
            duplicate_of_existing: false,
          },
          201,
        );
      }
      if (url.includes('/knowledge/sources/note-1')) {
        return jsonResponse({
          ...makeSource({ id: 'note-1', kind: 'note', title: 'Idea' }),
          versions: [],
          current_version: null,
        });
      }
      if (url.includes('/workspaces/ws-1/sources')) return jsonResponse([]);
      if (url.endsWith('/workspaces')) return jsonResponse([WORKSPACE]);
      return jsonResponse({}, 404);
    });

    await renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('tab', { name: /write a note/i }));
    await user.type(screen.getByLabelText(/^title$/i), 'Idea');
    await user.type(screen.getByLabelText(/^note$/i), 'A captured thought.');
    await user.click(screen.getByRole('button', { name: /save note/i }));

    expect(await screen.findByText(/as a versioned note/i)).toBeInTheDocument();
  });

  it('keeps the save button disabled until the note has content', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes('/workspaces/ws-1/sources')) return jsonResponse([]);
      if (url.endsWith('/workspaces')) return jsonResponse([WORKSPACE]);
      return jsonResponse({}, 404);
    });

    await renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole('tab', { name: /write a note/i }));

    const save = screen.getByRole('button', { name: /save note/i });
    expect(save).toBeDisabled();

    await user.type(screen.getByLabelText(/^note$/i), 'content');
    expect(save).toBeDisabled(); // still missing a title

    await user.type(screen.getByLabelText(/^title$/i), 'Title');
    expect(save).toBeEnabled();
  });

  it('surfaces a list error without inventing sources', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes('/workspaces/ws-1/sources')) {
        return jsonResponse(
          { error: { code: 'server_error', message: 'Sources unavailable.', request_id: 'r-1' } },
          500,
        );
      }
      if (url.endsWith('/workspaces')) return jsonResponse([WORKSPACE]);
      return jsonResponse({}, 404);
    });

    await renderPage();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/sources unavailable/i);
    });
    expect(screen.queryByText(/nothing submitted yet/i)).not.toBeInTheDocument();
  });
});
