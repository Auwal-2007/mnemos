import type { ReactNode } from 'react';
import './PageContainer.css';

export interface PageContainerProps {
  children: ReactNode;
  width?: 'default' | 'wide' | 'reading' | 'full';
}

/** Constrains and pads page content consistently across breakpoints. */
export function PageContainer({ children, width = 'default' }: PageContainerProps): JSX.Element {
  return <div className={`page-container page-container--${width}`}>{children}</div>;
}
