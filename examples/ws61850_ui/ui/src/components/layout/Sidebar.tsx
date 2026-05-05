import AccountTreeIcon from '@mui/icons-material/AccountTree';
import BugReportIcon from '@mui/icons-material/BugReport';
import DashboardIcon from '@mui/icons-material/Dashboard';
import RouterIcon from '@mui/icons-material/Router';
import SettingsIcon from '@mui/icons-material/Settings';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import StorageIcon from '@mui/icons-material/Storage';
import { Box, Drawer, List, ListItemButton, ListItemText, Typography } from '@mui/material';
import { Link, useRouterState } from '@tanstack/react-router';

export const SIDEBAR_WIDTH = 250;

const navItems = [
  { to: '/',            label: 'Dashboard',   icon: <DashboardIcon />,  gradient: 'linear-gradient(195deg,#42424a,#191919)', shadow: 'rgba(52,71,103,.4)' },
  { to: '/connections', label: 'Connections', icon: <RouterIcon />,      gradient: 'linear-gradient(195deg,#EC407A,#D81B60)', shadow: 'rgba(233,30,99,.4)' },
  { to: '/model',       label: 'Model',       icon: <AccountTreeIcon />, gradient: 'linear-gradient(195deg,#66BB6A,#43A047)', shadow: 'rgba(76,175,80,.4)' },
  { to: '/data',        label: 'Data',        icon: <StorageIcon />,     gradient: 'linear-gradient(195deg,#FFA726,#FB8C00)', shadow: 'rgba(251,140,0,.4)' },
  { to: '/reports',     label: 'Reports',     icon: <ShowChartIcon />,   gradient: 'linear-gradient(195deg,#49a3f1,#1A73E8)', shadow: 'rgba(26,115,232,.4)' },
  { to: '/diagnostics', label: 'Diagnostics', icon: <BugReportIcon />,   gradient: 'linear-gradient(195deg,#EF5350,#E53935)', shadow: 'rgba(244,67,53,.4)' },
  { to: '/settings',    label: 'Settings',    icon: <SettingsIcon />,    gradient: 'linear-gradient(195deg,#42424a,#191919)', shadow: 'rgba(52,71,103,.4)' },
] as const;

export function Sidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  return (
    <Drawer
      variant="permanent"
      sx={{
        width: SIDEBAR_WIDTH,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: SIDEBAR_WIDTH,
          boxSizing: 'border-box',
          background: '#fff',
          borderRight: 'none',
          boxShadow: '0 20px 27px 0 rgba(0,0,0,.05)',
          display: 'flex',
          flexDirection: 'column',
        },
      }}
    >
      {/* Brand */}
      <Box sx={{ px: 3, py: 2.5, borderBottom: '1px solid rgba(0,0,0,.06)', display: 'flex', alignItems: 'center', gap: 1.5 }}>
        <Box sx={{
          width: 32, height: 32, borderRadius: 2,
          background: 'linear-gradient(195deg,#42424a,#191919)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <Typography sx={{ color: '#fff', fontWeight: 900, fontSize: 14, lineHeight: 1 }}>61</Typography>
        </Box>
        <Box>
          <Typography sx={{ fontWeight: 700, fontSize: '0.875rem', color: '#344767', lineHeight: 1.2 }}>
            IEC 61850
          </Typography>
          <Typography variant="caption" sx={{ color: '#7b809a', textTransform: 'none', letterSpacing: 0 }}>
            RTI Demo UI
          </Typography>
        </Box>
      </Box>

      {/* Navigation */}
      <List sx={{ px: 2, pt: 2, flexGrow: 1 }}>
        {navItems.map((item) => {
          const isActive = item.to === '/' ? pathname === '/' : pathname.startsWith(item.to);
          return (
            <ListItemButton
              key={item.to}
              component={Link}
              to={item.to}
              sx={{
                borderRadius: 2, mb: 0.5, px: 2, py: 1, minHeight: 44, gap: 1.5,
                ...(isActive && {
                  background: 'linear-gradient(195deg,#49a3f1,#1A73E8)',
                  boxShadow: '0 4px 6px -1px rgba(0,0,0,.1), 0 2px 4px -1px rgba(26,115,232,.4)',
                }),
                '&:hover': isActive ? {} : { background: 'rgba(0,0,0,.04)', borderRadius: 2 },
              }}
            >
              <Box sx={{
                width: 32, height: 32, borderRadius: 1.5, flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#fff',
                background: isActive ? 'rgba(255,255,255,.2)' : item.gradient,
                boxShadow: isActive ? 'none' : `0 4px 20px 0 rgba(0,0,0,.14), 0 7px 10px -5px ${item.shadow}`,
                '& svg': { fontSize: 18 },
                transition: 'background 0.2s',
              }}>
                {item.icon}
              </Box>
              <ListItemText
                primary={item.label}
                slotProps={{ primary: { sx: {
                  fontSize: '0.8125rem',
                  fontWeight: isActive ? 700 : 500,
                  color: isActive ? '#fff' : '#344767',
                  lineHeight: 1,
                }}}}
              />
            </ListItemButton>
          );
        })}
      </List>

      <Box sx={{ px: 3, py: 2, borderTop: '1px solid rgba(0,0,0,.06)' }}>
        <Typography variant="caption" sx={{ color: '#7b809a', textTransform: 'none', letterSpacing: 0, fontSize: '0.7rem' }}>
          RTI BFF · IEC 61850 over WebSocket
        </Typography>
      </Box>
    </Drawer>
  );
}
