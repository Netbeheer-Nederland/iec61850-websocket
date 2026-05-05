import RouterIcon from '@mui/icons-material/Router';
import { Box, Button, Card, CardContent, Chip, Grid, Stack, TextField, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { type ConnectParams, type Target } from '../services/bffApi';
import { useConnectionStore } from '../stores/connectionStore';

const TARGET_META: Record<Target, { label: string; role: string; defaultConfig: Partial<ConnectParams> }> = {
  'rti-so': {
    label: 'RTI-SO',
    role: 'ws_server + iec_client',
    defaultConfig: { is_server: true, port: 9000, cp: 'cp1' },
  },
  'rti-fsp': {
    label: 'RTI-FSP',
    role: 'ws_client + iec_server',
    defaultConfig: { url: 'rti-so', port: 9100, cp: 'cp1', is_server: false, application_role: 'iec_server' },
  },
};

const STATE_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  connected:     'success',
  listening:     'success',
  connecting:    'warning',
  error:         'error',
  'not-connected': 'default',
};

function TargetCard({ target }: { target: Target }) {
  const meta       = TARGET_META[target];
  const connState  = useConnectionStore((s) => s.targets[target]);
  const loading    = useConnectionStore((s) => s.loading[target]);
  const error      = useConnectionStore((s) => s.error[target]);
  const connect    = useConnectionStore((s) => s.connect);
  const disconnect = useConnectionStore((s) => s.disconnect);

  const [url,  setUrl]  = useState(meta.defaultConfig.url  ?? '');
  const [port, setPort] = useState(String(meta.defaultConfig.port ?? ''));
  const [cp,   setCp]   = useState(meta.defaultConfig.cp   ?? 'cp1');

  const active = connState.connectionState === 'connected' || connState.connectionState === 'listening';
  const inProgress = connState.connectionState === 'connecting' || loading;

  const handleConnect = () => {
    const params: ConnectParams = {
      target,
      port: Number(port),
      cp,
      ...(meta.defaultConfig.is_server
        ? { is_server: true }
        : { url, is_server: false, application_role: meta.defaultConfig.application_role }),
    };
    void connect(params);
  };

  return (
    <Card>
      <CardContent sx={{ p: '20px 24px !important' }}>
        {/* Header */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box sx={{
              width: 36, height: 36, borderRadius: 2, flexShrink: 0,
              background: target === 'rti-so'
                ? 'linear-gradient(195deg,#66BB6A,#43A047)'
                : 'linear-gradient(195deg,#49a3f1,#1A73E8)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: target === 'rti-so'
                ? '0 4px 20px 0 rgba(0,0,0,.14), 0 7px 10px -5px rgba(76,175,80,.4)'
                : '0 4px 20px 0 rgba(0,0,0,.14), 0 7px 10px -5px rgba(26,115,232,.4)',
            }}>
              <RouterIcon sx={{ fontSize: 18, color: '#fff' }} />
            </Box>
            <Box>
              <Typography variant="h6" sx={{ lineHeight: 1.2 }}>{meta.label}</Typography>
              <Typography variant="caption" sx={{ color: '#7b809a', textTransform: 'none', letterSpacing: 0 }}>
                {meta.role}
              </Typography>
            </Box>
          </Box>
          <Chip
            label={connState.connectionState}
            color={STATE_COLOR[connState.connectionState] ?? 'default'}
            size="small"
            sx={{ fontWeight: 700 }}
          />
        </Box>

        {/* Form */}
        <Stack spacing={1.5}>
          {!meta.defaultConfig.is_server && (
            <TextField
              label="Host / URL"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              fullWidth
              size="small"
              disabled={active || inProgress}
            />
          )}
          <Stack direction="row" spacing={1.5}>
            <TextField
              label="Port"
              value={port}
              onChange={(e) => setPort(e.target.value)}
              fullWidth
              size="small"
              type="number"
              disabled={active || inProgress}
            />
            <TextField
              label="CP"
              value={cp}
              onChange={(e) => setCp(e.target.value)}
              fullWidth
              size="small"
              disabled={active || inProgress}
            />
          </Stack>

          {error && (
            <Typography variant="body2" color="error" sx={{ fontSize: '0.75rem' }}>{error}</Typography>
          )}

          <Stack direction="row" spacing={1} sx={{ pt: 0.5 }}>
            <Button
              variant="contained"
              color="info"
              size="small"
              onClick={handleConnect}
              disabled={loading || active}
            >
              {inProgress ? 'Starting…' : meta.defaultConfig.is_server ? 'Listen' : 'Connect'}
            </Button>
            <Button
              variant="outlined"
              size="small"
              onClick={() => void disconnect(target)}
              disabled={loading || connState.connectionState === 'not-connected'}
            >
              Disconnect
            </Button>
          </Stack>
        </Stack>

        {/* Connected detail */}
        {active && (
          <Box sx={{ mt: 2, p: 1.5, bgcolor: 'rgba(76,175,80,.08)', borderRadius: 2, border: '1px solid rgba(76,175,80,.2)' }}>
            <Typography variant="caption" sx={{ color: '#2e7d32', fontWeight: 600, display: 'block' }}>
              {connState.connectionState === 'listening' ? 'Listening' : 'Connected'}
              {connState.detail?.cp ? ` — CP: ${connState.detail.cp}` : ''}
            </Typography>
            {connState.detail?.associateId !== undefined && (
              <Typography variant="caption" sx={{ color: '#2e7d32', textTransform: 'none', letterSpacing: 0 }}>
                Associate ID: {String(connState.detail.associateId)}
              </Typography>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}

export function ConnectionPage() {
  const refreshStatuses = useConnectionStore((s) => s.refreshStatuses);

  useEffect(() => {
    void refreshStatuses();
    const id = setInterval(() => void refreshStatuses(), 4000);
    return () => clearInterval(id);
  }, [refreshStatuses]);

  return (
    <Box>
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <TargetCard target="rti-so" />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <TargetCard target="rti-fsp" />
        </Grid>

        {/* Instructions card */}
        <Grid size={{ xs: 12 }}>
          <Card>
            <CardContent sx={{ p: '20px 24px !important' }}>
              <Typography variant="h6" sx={{ mb: 1.5 }}>Demo setup</Typography>
              <Grid container spacing={2}>
                {[
                  ['RTI-SO (ws_server + iec_client)',
                   'BFF opens a WebSocket listener. RTI-FSP connects here, or an external field device. After listening, browse the model and read/write data.'],
                  ['RTI-FSP (ws_client + iec_server)',
                   'BFF dials out to the rti-so container on port 9100 and acts as an IEC 61850 server. RTI-SO can then read its data model.'],
                ].map(([label, desc]) => (
                  <Grid key={label} size={{ xs: 12, sm: 6 }}>
                    <Typography variant="caption" sx={{ display: 'block', mb: 0.5, fontWeight: 700 }}>{label}</Typography>
                    <Typography variant="body2">{desc}</Typography>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
