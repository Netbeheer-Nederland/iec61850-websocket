import AccessTimeIcon from '@mui/icons-material/AccessTime';
import AccountTreeIcon from '@mui/icons-material/AccountTree';
import RouterIcon from '@mui/icons-material/Router';
import ShowChartIcon from '@mui/icons-material/ShowChart';
import StorageIcon from '@mui/icons-material/Storage';
import { Box, Button, Card, CardContent, Chip, Grid, Typography } from '@mui/material';
import { Link } from '@tanstack/react-router';
import { useEffect } from 'react';
import { StatCard } from '../components/dashboard/StatCard';
import { TARGET_LABELS, type Target } from '../services/bffApi';
import { useConnectionStore } from '../stores/connectionStore';
import { useReportUpdateStore } from '../stores/reportUpdateStore';

const STATE_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  connected:       'success',
  listening:       'success',
  connecting:      'warning',
  error:           'error',
  'not-connected': 'default',
};

function ConnectionCard({ target }: { target: Target }) {
  const state = useConnectionStore((s) => s.targets[target]);
  const color = STATE_COLOR[state.connectionState] ?? 'default';
  const active = state.connectionState === 'connected' || state.connectionState === 'listening';

  return (
    <Card sx={{ height: '100%' }}>
      <CardContent sx={{ p: '20px 24px !important', height: '100%' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box sx={{
              width: 32, height: 32, borderRadius: 1.5, flexShrink: 0,
              background: target === 'rti-so'
                ? 'linear-gradient(195deg,#66BB6A,#43A047)'
                : 'linear-gradient(195deg,#49a3f1,#1A73E8)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <RouterIcon sx={{ fontSize: 16, color: '#fff' }} />
            </Box>
            <Typography sx={{ fontWeight: 700, fontSize: '0.875rem', color: '#344767' }}>
              {TARGET_LABELS[target]}
            </Typography>
          </Box>
          <Chip label={state.connectionState} color={color} size="small" sx={{ fontWeight: 700, fontSize: '0.65rem' }} />
        </Box>
        <Typography variant="caption" sx={{ color: '#7b809a', textTransform: 'none', letterSpacing: 0, display: 'block', mb: 1 }}>
          {target === 'rti-so' ? 'ws_server + iec_client' : 'ws_client + iec_server'}
        </Typography>
        {active && state.detail?.cp != null && (
          <Typography variant="caption" sx={{ color: '#2e7d32', fontWeight: 600, textTransform: 'none', letterSpacing: 0 }}>
            CP: {String(state.detail.cp)}
          </Typography>
        )}
        {!active && (
          <Button component={Link} to="/connections" size="small" color="info"
            sx={{ p: 0, fontSize: '0.75rem', fontWeight: 600, minWidth: 0 }}>
            Configure →
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const refreshStatuses = useConnectionStore((s) => s.refreshStatuses);
  const updateCount     = useReportUpdateStore((s) => s.updates.length);
  const isPolling       = useReportUpdateStore((s) => s.isPolling);
  const startPolling    = useReportUpdateStore((s) => s.startPolling);

  useEffect(() => {
    void refreshStatuses();
    if (!isPolling) startPolling();
  }, [refreshStatuses, isPolling, startPolling]);

  return (
    <Box>
      <Grid container spacing={3} sx={{ mt: 1 }}>
        {/* Connection status cards */}
        <Grid size={{ xs: 12, sm: 6, xl: 3 }}>
          <ConnectionCard target="rti-so" />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, xl: 3 }}>
          <ConnectionCard target="rti-fsp" />
        </Grid>

        {/* Report updates */}
        <Grid size={{ xs: 12, sm: 6, xl: 3 }}>
          <StatCard
            label="Report updates"
            value={updateCount.toLocaleString()}
            icon={<ShowChartIcon />}
            color="info"
            footer={
              <>
                <AccessTimeIcon sx={{ fontSize: 12, mr: 0.5 }} />
                {isPolling ? 'Polling active' : 'Polling stopped'}
              </>
            }
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, xl: 3 }}>
          <StatCard
            label="BFF targets"
            value="2"
            icon={<StorageIcon />}
            color="dark"
            footer={
              <>
                <AccountTreeIcon sx={{ fontSize: 12, mr: 0.5 }} />
                RTI-SO + RTI-FSP
              </>
            }
          />
        </Grid>
      </Grid>

      {/* Quick actions */}
      <Grid container spacing={3} sx={{ mt: 0.5 }}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent sx={{ p: '20px 24px !important' }}>
              <Typography variant="h6" sx={{ mb: 0.5 }}>Quick actions</Typography>
              <Typography variant="body2" sx={{ mb: 2 }}>
                Connect to RTI-SO / RTI-FSP, browse the IEC 61850 model, or read/write data.
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                <Button component={Link} to="/connections" variant="contained" color="info" size="small">
                  Connections
                </Button>
                <Button component={Link} to="/model" variant="outlined" size="small">
                  Model
                </Button>
                <Button component={Link} to="/data" variant="outlined" size="small">
                  Data
                </Button>
                <Button component={Link} to="/reports" variant="outlined" size="small">
                  Reports
                </Button>
                <Button component={Link} to="/diagnostics" variant="outlined" size="small">
                  Diagnostics
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent sx={{ p: '20px 24px !important' }}>
              <Typography variant="h6" sx={{ mb: 0.5 }}>Demo setup</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>RTI-FSP</strong> (rti-fsp container) dials into <strong>RTI-SO</strong> (rti-so:9100) on startup.
              </Typography>
              <Typography variant="body2">
                Use <em>Connections</em> to attach the BFF to either component, then browse its model or subscribe to reports via <em>Data</em>.
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
