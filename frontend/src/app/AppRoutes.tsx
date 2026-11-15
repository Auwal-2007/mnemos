import { Route, Routes } from 'react-router-dom';
import { AppShell } from '../components/layout/AppShell';
import { AgentDirectoryPage } from '../features/agents/AgentDirectoryPage';
import { AgentConversationPage } from '../features/conversations/AgentConversationPage';
import { ConversationsPage } from '../features/conversations/ConversationsPage';
import { OrchestratorConversationPage } from '../features/conversations/OrchestratorConversationPage';
import { HomePage } from '../features/home/HomePage';
import { KnowledgePage } from '../features/knowledge/KnowledgePage';
import { SettingsPage } from '../features/settings/SettingsPage';
import { SignInPage } from '../features/auth/SignInPage';
import { NotFoundPage } from '../features/system/NotFoundPage';

/**
 * Route table. Every route renders a real, implemented surface — planned
 * areas use an explicit placeholder that states their status.
 */
export function AppRoutes(): JSX.Element {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="conversations" element={<ConversationsPage />} />
        <Route path="conversations/orchestrator" element={<OrchestratorConversationPage />} />
        <Route path="conversations/agent/:agentId" element={<AgentConversationPage />} />
        <Route path="agents" element={<AgentDirectoryPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="sources" element={<KnowledgePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
      <Route path="/sign-in" element={<SignInPage />} />
    </Routes>
  );
}
