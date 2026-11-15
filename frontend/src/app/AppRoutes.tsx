import { Route, Routes } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { AgentDirectoryPage } from '../features/agents/AgentDirectoryPage';
import { AgentConversationPage } from '../features/conversations/AgentConversationPage';
import { ConversationsPage } from '../features/conversations/ConversationsPage';
import { OrchestratorConversationPage } from '../features/conversations/OrchestratorConversationPage';
import { LandingPage } from '../features/landing/LandingPage';
import { DashboardPage } from '../features/home/DashboardPage';
import { KnowledgePage } from '../features/knowledge/KnowledgePage';
import { SettingsPage } from '../features/settings/SettingsPage';
import { SignInPage } from '../features/auth/SignInPage';
import { NotFoundPage } from '../features/system/NotFoundPage';
import { SystemStatusPage } from '../features/home/SystemStatusPage';

/**
 * Route table.
 *
 * The public site owns `/`; the authenticated product lives under `/app`.
 * That split is deliberate: a marketing shell and a work surface have
 * different chrome, and conflating them is what makes product sites feel
 * like a dashboard with a hero bolted on.
 *
 * Every route renders a real, implemented surface. Areas that are not built
 * say so explicitly rather than showing a convincing shell with nothing
 * behind it.
 */
export function AppRoutes(): JSX.Element {
  return (
    <Routes>
      {/* Public */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/sign-in" element={<SignInPage />} />

      {/* Product */}
      <Route path="/app" element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="sources" element={<KnowledgePage />} />
        <Route path="conversations" element={<ConversationsPage />} />
        <Route path="conversations/orchestrator" element={<OrchestratorConversationPage />} />
        <Route path="conversations/agent/:agentId" element={<AgentConversationPage />} />
        <Route path="agents" element={<AgentDirectoryPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="system" element={<SystemStatusPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
