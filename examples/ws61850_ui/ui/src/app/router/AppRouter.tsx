import { RouterProvider, createRouter, createRootRoute, createRoute } from '@tanstack/react-router';
import { AppShell } from '../../components/layout/AppShell';
import { DashboardPage }    from '../../pages/DashboardPage';
import { ConnectionPage }   from '../../pages/ConnectionPage';
import { ModelPage }        from '../../pages/ModelPage';
import { DataPage }         from '../../pages/DataPage';
import { StreamPage }       from '../../pages/StreamPage';
import { PointPage }        from '../../pages/PointPage';
import { DiagnosticsPage }  from '../../pages/DiagnosticsPage';
import { SettingsPage }     from '../../pages/SettingsPage';

const rootRoute = createRootRoute({ component: AppShell });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: DashboardPage,
});

const connectionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/connections',
  component: ConnectionPage,
});

const modelRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/model',
  component: ModelPage,
});

const dataRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/data',
  component: DataPage,
});

const streamRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/reports',
  component: StreamPage,
});

const pointRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/points/$pointRef',
  component: PointPage,
});

const diagnosticsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/diagnostics',
  component: DiagnosticsPage,
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/settings',
  component: SettingsPage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  connectionsRoute,
  modelRoute,
  dataRoute,
  streamRoute,
  pointRoute,
  diagnosticsRoute,
  settingsRoute,
]);

const router = createRouter({ routeTree });

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

export function AppRouter() {
  return <RouterProvider router={router} />;
}
