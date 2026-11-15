import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { App } from './App';

describe('App (Phase 0 shell)', () => {
  it('renders the MNEMOS title', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'MNEMOS' })).toBeDefined();
  });

  it('states the Phase 0 status', () => {
    render(<App />);
    expect(screen.getByText(/Phase 0/)).toBeDefined();
  });
});
