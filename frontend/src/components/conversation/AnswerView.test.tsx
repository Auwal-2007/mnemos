import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AnswerView } from './AnswerView';
import type { Answer, Citation } from '../../lib/api/types';

function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    provenance_id: 'prov-1',
    chunk_id: 'chunk-1',
    source_id: 'src-1',
    source_title: 'Visa Requirements',
    source_kind: 'document',
    version_number: 1,
    page: 2,
    start_offset: 0,
    end_offset: 120,
    excerpt: 'A passport must remain valid for at least six months.',
    information_status: 'current',
    ...overrides,
  };
}

function answer(overrides: Partial<Answer> = {}): Answer {
  return {
    answer_id: 'ans-1',
    status: 'answered',
    content: 'A passport must be valid for six months beyond your return date.',
    abstention_reason: null,
    claims: [{ text: 'A passport must be valid for six months.', citations: [citation()] }],
    evidence_considered: 4,
    evidence_cited: 1,
    evidence: [citation()],
    degraded_reason: null,
    execution: {
      id: 'exec-1',
      agent_role: 'orchestrator',
      model_id: 'test/model',
      status: 'succeeded',
      latency_ms: 812,
      prompt_tokens: 100,
      completion_tokens: 40,
      total_tokens: 140,
    },
    ...overrides,
  };
}

describe('AnswerView', () => {
  it('renders an answered response with its claims and citations', () => {
    render(<AnswerView answer={answer()} onInspectEvidence={() => undefined} />);
    expect(screen.getByText(/six months beyond your return date/i)).toBeInTheDocument();
    expect(screen.getByText(/a passport must be valid for six months\./i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /visa requirements/i })).toBeInTheDocument();
  });

  it('opens the provenance inspector when a citation is activated', () => {
    const onInspect = vi.fn();
    render(<AnswerView answer={answer()} onInspectEvidence={onInspect} />);
    fireEvent.click(screen.getByRole('button', { name: /visa requirements/i }));
    expect(onInspect).toHaveBeenCalledTimes(1);
    expect(onInspect.mock.calls[0][0].chunk_id).toBe('chunk-1');
  });

  it('renders an abstention as a stated result rather than an error', () => {
    render(
      <AnswerView
        answer={answer({
          status: 'abstained',
          content: '',
          claims: [],
          evidence: [],
          evidence_cited: 0,
          abstention_reason: 'No indexed source addresses this question.',
        })}
        onInspectEvidence={() => undefined}
      />,
    );
    expect(screen.getByText(/no answer given/i)).toBeInTheDocument();
    expect(screen.getByText(/no indexed source addresses this question/i)).toBeInTheDocument();
    // An abstention must not wear an error role; it is the designed outcome.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('surfaces a degraded answer with the reason attached', () => {
    render(
      <AnswerView
        answer={answer({ degraded_reason: 'Semantic search is not configured.' })}
        onInspectEvidence={() => undefined}
      />,
    );
    expect(screen.getByText(/degraded/i)).toBeInTheDocument();
    expect(screen.getByText(/semantic search is not configured/i)).toBeInTheDocument();
  });

  it('marks a superseded citation so an outdated source is visible', () => {
    const superseded = citation({ information_status: 'superseded' });
    render(
      <AnswerView
        answer={answer({
          claims: [{ text: 'Fee was 85 USD.', citations: [superseded] }],
          evidence: [superseded],
        })}
        onInspectEvidence={() => undefined}
      />,
    );
    expect(screen.getByText(/superseded/i)).toBeInTheDocument();
  });

  it('shows per-claim verification when it is supplied', () => {
    render(
      <AnswerView
        answer={answer()}
        onInspectEvidence={() => undefined}
        verificationById={{
          'A passport must be valid for six months.': {
            support: 'supported',
            note: '92% of the claim appears in the cited evidence.',
          },
        }}
      />,
    );
    expect(screen.getByText('Supported')).toBeInTheDocument();
    expect(screen.getByText(/92% of the claim/i)).toBeInTheDocument();
  });

  it('reports how much evidence was considered and cited', () => {
    render(<AnswerView answer={answer()} onInspectEvidence={() => undefined} />);
    expect(screen.getByText(/4 passages considered, 1 cited/i)).toBeInTheDocument();
  });

  it('does not invent citations when the backend supplied none', () => {
    render(
      <AnswerView
        answer={answer({ claims: [], evidence: [], evidence_cited: 0, content: 'Something.' })}
        onInspectEvidence={() => undefined}
      />,
    );
    expect(screen.queryAllByRole('button')).toHaveLength(0);
    expect(screen.getByText(/none cited/i)).toBeInTheDocument();
  });
});
