import { AppBar, Box, Chip, Toolbar, Typography } from '@mui/material';
import { useSessionStore } from '../../stores/sessionStore';

export function StatusBar() {
  const socketState = useSessionStore((s) => s.socketState);
  const endpoint = useSessionStore((s) => s.endpointUrl);
  const lastMessageAt = useSessionStore((s) => s.lastMessageAt);

  return (
    <AppBar position="fixed" color="default" sx={{ top: 'auto', bottom: 0 }}>
      <Toolbar sx={{ gap: 2 }}>
        <Typography variant="body2">Endpoint: {endpoint}</Typography>
        <Chip label={socketState} size="small" color={socketState === 'connected' ? 'success' : socketState === 'error' ? 'error' : 'warning'} />
        <Typography variant="body2">Last frame: {lastMessageAt ? new Date(lastMessageAt).toLocaleTimeString() : '—'}</Typography>
        <Box sx={{ flexGrow: 1 }} />
        <Typography variant="body2">RTI Demo UI</Typography>
      </Toolbar>
    </AppBar>
  );
}
