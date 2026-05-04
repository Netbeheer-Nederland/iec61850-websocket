import { Box, Button, Card, CardContent, Chip, Divider, FormControlLabel, Stack, Switch, TextField, Typography } from '@mui/material';
import { useSessionStore } from '../stores/sessionStore';
import { websocketClient } from '../services/websocketClient';

export function SessionPage() {
  const endpointUrl       = useSessionStore((s) => s.endpointUrl);
  const setEndpoint       = useSessionStore((s) => s.setEndpoint);
  const socketState       = useSessionStore((s) => s.socketState);
  const reconnectEnabled  = useSessionStore((s) => s.reconnectEnabled);
  const setReconnectEnabled = useSessionStore((s) => s.setReconnectEnabled);
  const lastMessageAt     = useSessionStore((s) => s.lastMessageAt);
  const connectedAt       = useSessionStore((s) => s.connectedAt);

  const connected = socketState === 'connected';
  const chipColor = connected ? 'success' : socketState === 'error' ? 'error' : 'warning';

  return (
    <Box>
      <Card>
        <CardContent sx={{ p: '24px !important' }}>
          <Typography variant="h6" sx={{ mb: 0.5 }}>WebSocket endpoint</Typography>
          <Typography variant="body2" sx={{ mb: 3 }}>
            Enter a WebSocket URL to connect. Use <code>mock://demo</code> for the built-in simulator.
          </Typography>

          <Stack spacing={2.5}>
            <TextField
              label="Endpoint URL"
              value={endpointUrl}
              onChange={(e) => setEndpoint(e.target.value)}
              fullWidth
              helperText="e.g. ws://192.168.1.10:9000  ·  wss://device.example.com  ·  mock://demo"
            />

            <FormControlLabel
              control={
                <Switch
                  checked={reconnectEnabled}
                  onChange={(e) => setReconnectEnabled(e.target.checked)}
                  color="info"
                />
              }
              label={<Typography variant="body1" sx={{ color: 'text.primary' }}>Auto-reconnect on disconnect</Typography>}
            />

            <Stack direction="row" spacing={1.5}>
              <Button
                variant="contained"
                color="info"
                onClick={() => websocketClient.connect(endpointUrl)}
              >
                Connect
              </Button>
              <Button
                variant="outlined"
                onClick={() => websocketClient.disconnect()}
              >
                Disconnect
              </Button>
              <Button
                variant="text"
                onClick={() => websocketClient.send({ type: 'model.request' })}
              >
                Refresh model
              </Button>
            </Stack>
          </Stack>
        </CardContent>

        <Divider />

        <CardContent sx={{ p: '16px 24px !important' }}>
          <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
            <Chip
              label={socketState}
              color={chipColor}
              size="small"
              sx={{ fontWeight: 700 }}
            />
            <Typography variant="caption" sx={{ color: '#7b809a', textTransform: 'none', letterSpacing: 0 }}>
              Connected at: <strong>{connectedAt ? new Date(connectedAt).toLocaleString() : '—'}</strong>
            </Typography>
            <Typography variant="caption" sx={{ color: '#7b809a', textTransform: 'none', letterSpacing: 0 }}>
              Last frame: <strong>{lastMessageAt ? new Date(lastMessageAt).toLocaleString() : '—'}</strong>
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
