import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AccountHqPage } from '../features/account/AccountHqPage';
import { AccountLayout } from '../features/account/AccountLayout';
import { AccountSettingsPage } from '../features/account/AccountSettingsPage';
import { FleetOverviewPage } from '../features/fleet/FleetOverviewPage';
import { PipelineOpsPage } from '../features/pipeline/PipelineOpsPage';
import { PostDetailPage } from '../features/posts/PostDetailPage';
import { PostsExplorerPage } from '../features/posts/PostsExplorerPage';
import { ReferencesLabPage } from '../features/references/ReferencesLabPage';
import { VoiceExperimentsPage } from '../features/voice/VoiceExperimentsPage';
import { AppLayout } from './AppLayout';

const basename = process.env.PUBLIC_URL || undefined;

export const router = createBrowserRouter(
  [
    {
      path: '/',
      element: <AppLayout />,
      children: [
        { index: true, element: <FleetOverviewPage /> },
        {
          path: 'accounts/:accountId',
          element: <AccountLayout />,
          children: [
            { index: true, element: <AccountHqPage /> },
            { path: 'posts', element: <PostsExplorerPage /> },
            { path: 'posts/:tweetId', element: <PostDetailPage /> },
            { path: 'references', element: <ReferencesLabPage /> },
            { path: 'pipeline', element: <PipelineOpsPage /> },
            { path: 'voice', element: <VoiceExperimentsPage /> },
            { path: 'settings', element: <AccountSettingsPage /> },
          ],
        },
        { path: '*', element: <Navigate to="/" replace /> },
      ],
    },
  ],
  { basename }
);
