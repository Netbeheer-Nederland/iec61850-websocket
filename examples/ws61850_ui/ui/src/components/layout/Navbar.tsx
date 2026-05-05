import RouterIcon from '@mui/icons-material/Router';
import WifiOffIcon from '@mui/icons-material/WifiOff';
import { AppBar, Box, Chip, Toolbar, Typography } from '@mui/material';
import { useRouterState } from '@tanstack/react-router';
import { useConnectionStore } from '../../stores/connectionStore';
import { SIDEBAR_WIDTH } from './Sidebar';

const routeLabels: Record<string, string> = {
  '/':            'Dashboard',
  '/connections': 'Connections',
  '/model':       'Model Explorer',
  '/data':        'Data',
  '/reports':     'Report Updates',
  '/diagnostics': 'Diagnostics',
  '/settings':    'Settings',
};

function pageTitle(pathname: string): string {
  if (pathname.startsWith('/points/')) return 'Point Detail';
  return routeLabels[pathname] ?? pathname.replace('/', '');
}

function parentLabel(pathname: string): string {
  if (pathname.startsWith('/points/')) return 'Reports';
  return 'Pages';
}

export function Navbar() {
  const pathname  = useRouterState({ select: (s) => s.location.pathname });
  const soState   = useConnectionStore((s) => s.targets['rti-so'].connectionState);
  const fspState  = useConnectionStore((s) => s.targets['rti-fsp'].connectionState);

  const activeTargets = [
    soState  === 'connected' || soState  === 'listening' ? 'RTI-SO'  : null,
    fspState === 'connected' || fspState === 'listening' ? 'RTI-FSP' : null,
  ].filter(Boolean);

  return (
    <AppBar
      position="fixed"
      elevation={0}
      sx={{
        left: SIDEBAR_WIDTH,
        width: `calc(100% - ${SIDEBAR_WIDTH}px)`,
        background: 'rgba(255,255,255,0.8)',
        backdropFilter: 'saturate(200%) blur(30px)',
        borderBottom: '1px solid rgba(0,0,0,.06)',
        color: 'text.primary',
      }}
    >
      <Toolbar sx={{ minHeight: '60px !important', px: '24px !important', gap: 1 }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography
            variant="caption"
            sx={{ color: '#7b809a', fontWeight: 400, letterSpacing: 0, textTransform: 'none', display: 'block', lineHeight: 1 }}
          >
            {parentLabel(pathname)} / {pageTitle(pathname)}
          </Typography>
          <Typography variant="h6" sx={{ lineHeight: 1.3, mt: 0.25 }}>
            {pageTitle(pathname)}
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {activeTargets.length > 0 ? (
            activeTargets.map((label) => (
              <Chip
                key={label}
                icon={<RouterIcon sx={{ fontSize: '14px !important' }} />}
                label={label}
                color="success"
                size="small"
                sx={{ fontWeight: 700, fontSize: '0.65rem' }}
              />
            ))
          ) : (
            <Chip
              icon={<WifiOffIcon sx={{ fontSize: '14px !important' }} />}
              label="not connected"
              color="default"
              size="small"
              sx={{ fontWeight: 700, fontSize: '0.65rem' }}
            />
          )}
        </Box>
      </Toolbar>
    </AppBar>
  );
}
