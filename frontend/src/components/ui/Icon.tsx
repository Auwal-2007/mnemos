/**
 * Iconography.
 *
 * Lucide is the single icon source: one stroke weight (1.5), one 24-unit
 * grid, one visual language. The public API keeps the original `Icon`
 * component and `IconName` union so existing call sites keep working; the
 * names are MNEMOS-semantic ("provenance", "supersede") rather than raw
 * Lucide names, so a future swap touches only this file.
 */

import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Box,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  Clock,
  Command,
  Compass,
  CornerDownLeft,
  Cpu,
  Database,
  Download,
  Eye,
  FileText,
  Filter,
  Fingerprint,
  Folder,
  GitBranch,
  Hash,
  History,
  Info,
  Layers,
  LayoutDashboard,
  Library,
  Link2,
  ListFilter,
  Loader2,
  Lock,
  LogOut,
  Menu,
  MessageSquare,
  Minus,
  Moon,
  MoreHorizontal,
  Network,
  Pause,
  PenLine,
  Play,
  Plus,
  Quote,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Split,
  Square,
  Sun,
  Trash2,
  Upload,
  User,
  Users,
  X,
  Zap,
  type LucideIcon,
} from 'lucide-react';

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
  | 'chevron-right'
  | 'chevron-down'
  | 'arrow-left'
  | 'arrow-right'
  | 'external'
  | 'send'
  | 'search'
  | 'filter'
  | 'document'
  | 'note'
  | 'history'
  | 'user'
  | 'logout'
  | 'theme'
  | 'sun'
  | 'moon'
  | 'info'
  | 'check'
  | 'check-all'
  | 'alert'
  | 'plus'
  | 'minus'
  | 'upload'
  | 'download'
  | 'trash'
  | 'refresh'
  | 'reset'
  | 'spinner'
  | 'more'
  | 'quote'
  | 'citation'
  | 'provenance'
  | 'version'
  | 'supersede'
  | 'conflict'
  | 'verified'
  | 'unverified'
  | 'lock'
  | 'fingerprint'
  | 'orchestrator'
  | 'retrieval'
  | 'memory'
  | 'verification'
  | 'graph'
  | 'layers'
  | 'database'
  | 'cpu'
  | 'spark'
  | 'zap'
  | 'library'
  | 'compass'
  | 'dashboard'
  | 'box'
  | 'clock'
  | 'eye'
  | 'linking'
  | 'command'
  | 'enter'
  | 'play'
  | 'pause'
  | 'stop'
  | 'users'
  | 'branch'
  | 'hash'
  | 'circled-dot';

const REGISTRY: Record<IconName, LucideIcon> = {
  home: LayoutDashboard,
  workspace: Folder,
  conversations: MessageSquare,
  agents: Network,
  sources: Library,
  settings: Settings,
  menu: Menu,
  close: X,
  'chevron-left': ChevronLeft,
  'chevron-right': ChevronRight,
  'chevron-down': ChevronDown,
  'arrow-left': ArrowLeft,
  'arrow-right': ArrowRight,
  external: ArrowUpRight,
  send: Send,
  search: Search,
  filter: ListFilter,
  document: FileText,
  note: PenLine,
  history: History,
  user: User,
  logout: LogOut,
  theme: Sun,
  sun: Sun,
  moon: Moon,
  info: Info,
  check: Check,
  'check-all': CheckCheck,
  alert: AlertTriangle,
  plus: Plus,
  minus: Minus,
  upload: Upload,
  download: Download,
  trash: Trash2,
  refresh: RefreshCw,
  reset: RotateCcw,
  spinner: Loader2,
  more: MoreHorizontal,
  quote: Quote,
  citation: BookOpen,
  provenance: Fingerprint,
  version: GitBranch,
  supersede: History,
  conflict: Split,
  verified: ShieldCheck,
  unverified: Eye,
  lock: Lock,
  fingerprint: Fingerprint,
  orchestrator: Compass,
  retrieval: Search,
  memory: Database,
  verification: ShieldCheck,
  graph: Network,
  layers: Layers,
  database: Database,
  cpu: Cpu,
  spark: Sparkles,
  zap: Zap,
  library: Library,
  compass: Compass,
  dashboard: LayoutDashboard,
  box: Box,
  clock: Clock,
  eye: Eye,
  linking: Link2,
  command: Command,
  enter: CornerDownLeft,
  play: Play,
  pause: Pause,
  stop: Square,
  users: Users,
  branch: GitBranch,
  hash: Hash,
  'circled-dot': CircleDot,
};

export interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  /** Stroke weight. 1.5 is the system default; 1.75 for emphasis at small sizes. */
  strokeWidth?: number;
  /** Provide a label when the icon is the only content of a control. */
  label?: string;
}

/**
 * Renders one icon. Decorative by default (`aria-hidden`), because icons here
 * always accompany text; pass `label` when that is not true.
 */
export function Icon({
  name,
  size = 20,
  className,
  strokeWidth = 1.5,
  label,
}: IconProps): JSX.Element {
  const Component = REGISTRY[name];
  return (
    <Component
      size={size}
      strokeWidth={strokeWidth}
      className={className}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? 'img' : undefined}
      absoluteStrokeWidth={false}
      focusable="false"
    />
  );
}

/** Re-exported for components that need a raw Lucide glyph (e.g. spinners). */
export { Loader2, ArrowRight, ArrowUpRight, Filter, RefreshCw, Filter as FilterIcon };
