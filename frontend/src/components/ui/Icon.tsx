/**
 * Minimal inline icon set (stroke-based, 1.5px, 20px grid).
 * Inline SVGs avoid an icon dependency and inherit currentColor.
 */

export type IconName =
  | 'home'
  | 'workspace'
  | 'conversations'
  | 'agents'
  | 'sources'
  | 'settings'
  | 'menu'
  | 'close'
  | 'chevron-left'
  | 'send'
  | 'search'
  | 'document'
  | 'note'
  | 'history'
  | 'user'
  | 'logout'
  | 'theme'
  | 'info'
  | 'check'
  | 'alert'
  | 'plus';

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
}

const paths: Record<IconName, JSX.Element> = {
  home: (
    <path d="M3 9.5 10 3l7 6.5V17a1 1 0 0 1-1 1h-4v-5H8v5H4a1 1 0 0 1-1-1V9.5Z" />
  ),
  workspace: (
    <>
      <path d="M3 5.5A1.5 1.5 0 0 1 4.5 4h3.2l1.5 2h6.3A1.5 1.5 0 0 1 17 7.5v7A1.5 1.5 0 0 1 15.5 16h-11A1.5 1.5 0 0 1 3 14.5v-9Z" />
    </>
  ),
  conversations: (
    <path d="M3 5.5A1.5 1.5 0 0 1 4.5 4h11A1.5 1.5 0 0 1 17 5.5v7a1.5 1.5 0 0 1-1.5 1.5H8l-4 3v-3H4.5A1.5 1.5 0 0 1 3 12.5v-7Z" />
  ),
  agents: (
    <>
      <circle cx="7" cy="7" r="2.5" />
      <circle cx="13.5" cy="10.5" r="2" />
      <path d="M2.5 16c0-2 2-3.5 4.5-3.5s4.5 1.5 4.5 3.5M11.5 16c0-1.4 1.2-2.5 2.7-2.5 1.2 0 2.3.7 2.8 1.8" />
    </>
  ),
  sources: (
    <>
      <path d="M4 4h8l4 4v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z" />
      <path d="M12 4v4h4" />
    </>
  ),
  settings: (
    <>
      <circle cx="10" cy="10" r="2.5" />
      <path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4" />
    </>
  ),
  menu: <path d="M3 5h14M3 10h14M3 15h14" />,
  close: <path d="M5 5l10 10M15 5 5 15" />,
  'chevron-left': <path d="M12 4 6 10l6 6" />,
  send: <path d="M3 10l14-6-5 13-2.5-5L3 10Z" />,
  search: (
    <>
      <circle cx="9" cy="9" r="5.5" />
      <path d="M13.2 13.2 17 17" />
    </>
  ),
  document: (
    <>
      <path d="M5 3h6l4 4v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z" />
      <path d="M11 3v4h4M7 11h5M7 14h5" />
    </>
  ),
  note: (
    <>
      <path d="M4 4h12v12H4z" />
      <path d="M7 7h6M7 10h6M7 13h3" />
    </>
  ),
  history: (
    <>
      <path d="M10 5v5l3 2" />
      <path d="M3.5 8.5A7 7 0 1 1 3 12" />
      <path d="M3 4v4.5h4.5" />
    </>
  ),
  user: (
    <>
      <circle cx="10" cy="7" r="3" />
      <path d="M4 16.5c0-2.8 2.7-4.5 6-4.5s6 1.7 6 4.5" />
    </>
  ),
  logout: (
    <path d="M8 4H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3M12.5 7 16 10l-3.5 3M16 10H8" />
  ),
  theme: (
    <>
      <circle cx="10" cy="10" r="4" />
      <path d="M10 2v1.5M10 16.5V18M2 10h1.5M16.5 10H18M4.3 4.3l1 1M14.7 14.7l1 1M15.7 4.3l-1 1M5.3 14.7l-1 1" />
    </>
  ),
  info: (
    <>
      <circle cx="10" cy="10" r="7.5" />
      <path d="M10 9v5M10 6.5V7" />
    </>
  ),
  check: <path d="M4 10.5 8 14.5l8-9" />,
  alert: (
    <>
      <path d="M10 3.5 17.5 16.5h-15L10 3.5Z" />
      <path d="M10 8v4M10 14v.5" />
    </>
  ),
  plus: <path d="M10 4v12M4 10h12" />,
};

export function Icon({ name, size = 20, className }: IconProps): JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {paths[name]}
    </svg>
  );
}
