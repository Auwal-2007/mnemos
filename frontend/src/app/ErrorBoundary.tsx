import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from '../components/ui/Button';
import './ErrorBoundary.css';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Last-resort boundary for render-time failures. Keeps the application
 * shell intact and offers recovery instead of a blank screen.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Never log user content; the message plus component stack is enough.
    console.error('Unhandled render error:', error.message, info.componentStack);
  }

  private handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="crash" role="alert">
        <div className="crash__panel">
          <p className="crash__eyebrow">MNEMOS</p>
          <h1 className="crash__title">The interface hit an unexpected error</h1>
          <p className="crash__message">
            Your data has not been affected. Reload the interface to continue; if the problem
            persists, check the browser console for details.
          </p>
          <div className="crash__actions">
            <Button variant="primary" onClick={this.handleReset}>
              Try again
            </Button>
            <Button variant="secondary" onClick={() => window.location.reload()}>
              Reload application
            </Button>
          </div>
        </div>
      </div>
    );
  }
}
