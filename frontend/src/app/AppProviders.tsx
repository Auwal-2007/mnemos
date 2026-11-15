import type { ReactNode } from 'react';
import { AuthProvider } from '../lib/auth';
import { ErrorBoundary } from './ErrorBoundary';
import { ThemeProvider } from './ThemeProvider';
import { ToastProvider } from './ToastProvider';

/** Composition root for cross-cutting providers. */
export function AppProviders({ children }: { children: ReactNode }): JSX.Element {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <AuthProvider>
          <ToastProvider>{children}</ToastProvider>
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
