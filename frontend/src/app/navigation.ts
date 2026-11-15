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
  /** Keyboard hint for the command palette and compact rail tooltips. */
  hint?: string;
}

export interface NavGroup {
  id: string;
  label: string;
  items: NavItem[];
}

/**
 * Single source of navigation truth.
 *
 * Items are grouped because the product has three genuinely different kinds
 * of surface: what you own (the corpus), what you can ask (conversation), and
 * how the machine is configured. A flat list of six links hides that
 * structure and is what makes a sidebar feel generic.
 */
export const navigationGroups: NavGroup[] = [
  {
    id: 'workspace',
    label: 'Workspace',
    items: [
      {
        id: 'home',
        label: 'Overview',
        path: '/app',
        icon: 'home',
        status: 'available',
        hint: 'G then O',
      },
      {
        id: 'knowledge',
        label: 'Knowledge',
        path: '/app/knowledge',
        icon: 'workspace',
        status: 'available',
        hint: 'G then K',
        note: 'Submit documents and notes; retrieval arrives in a later phase.',
      },
      {
        id: 'sources',
        label: 'Sources & evidence',
        path: '/app/sources',
        icon: 'sources',
        status: 'available',
        note: 'Inspect provenance for everything you have added.',
      },
    ],
  },
  {
    id: 'intelligence',
    label: 'Intelligence',
    items: [
      {
        id: 'conversations',
        label: 'Conversations',
        path: '/app/conversations',
        icon: 'conversations',
        status: 'available',
        hint: 'G then C',
        note: 'Interface foundation only — agents are not yet connected.',
      },
      {
        id: 'agents',
        label: 'Agents',
        path: '/app/agents',
        icon: 'agents',
        status: 'available',
        hint: 'G then A',
        note: 'Directory of planned specialist roles.',
      },
    ],
  },
  {
    id: 'system',
    label: 'System',
    items: [
      {
        id: 'settings',
        label: 'Settings',
        path: '/app/settings',
        icon: 'settings',
        status: 'available',
      },
      {
        id: 'system',
        label: 'Deployment',
        path: '/app/system',
        icon: 'cpu',
        status: 'available',
      },
    ],
  },
];

/** Flattened, for command-palette search and legacy call sites. */
export const primaryNavigation: NavItem[] = navigationGroups.flatMap((group) => group.items);

export const agentPaths = {
  directory: '/app/agents',
  conversation: (agentId: string) => `/app/conversations/agent/${agentId}`,
  orchestrated: '/app/conversations/orchestrator',
} as const;

/** Routes reachable from the command palette that are not sidebar items. */
export const paletteExtras: NavItem[] = [
  {
    id: 'orchestrator',
    label: 'Orchestrator conversation',
    path: '/app/conversations/orchestrator',
    icon: 'orchestrator',
    status: 'available',
  },
  {
    id: 'landing',
    label: 'Public site',
    path: '/',
    icon: 'compass',
    status: 'available',
  },
];
