import type { IconName } from '../components/ui/Icon';

export type NavStatus = 'available' | 'planned';

export interface NavItem {
  id: string;
  label: string;
  path: string;
  icon: IconName;
  status: NavStatus;
  /** Shown in the UI so nothing pretends to be further along than it is. */
  note?: string;
}

/**
 * Single source of navigation truth. `status: 'planned'` routes render an
 * explicit placeholder — they are navigation destinations, not working
 * features, and the UI says so.
 */
export const primaryNavigation: NavItem[] = [
  {
    id: 'home',
    label: 'Home',
    path: '/',
    icon: 'home',
    status: 'available',
  },
  {
    id: 'knowledge',
    label: 'Knowledge Workspace',
    path: '/knowledge',
    icon: 'workspace',
    status: 'available',
    note: 'Submit documents and notes; retrieval arrives in a later phase.',
  },
  {
    id: 'conversations',
    label: 'Conversations',
    path: '/conversations',
    icon: 'conversations',
    status: 'available',
    note: 'Interface foundation only — agents are not yet connected.',
  },
  {
    id: 'agents',
    label: 'Agents',
    path: '/agents',
    icon: 'agents',
    status: 'available',
    note: 'Directory of planned specialist roles.',
  },
  {
    id: 'sources',
    label: 'Sources & Evidence',
    path: '/sources',
    icon: 'sources',
    status: 'available',
    note: 'Submit and inspect your sources in the knowledge workspace.',
  },
  {
    id: 'settings',
    label: 'Settings',
    path: '/settings',
    icon: 'settings',
    status: 'available',
  },
];

export const agentPaths = {
  directory: '/agents',
  conversation: (agentId: string) => `/conversations/agent/${agentId}`,
  orchestrated: '/conversations/orchestrator',
} as const;
