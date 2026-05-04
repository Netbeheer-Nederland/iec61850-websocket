import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import RefreshIcon from '@mui/icons-material/Refresh';
import { Box, Button, Card, CardContent, Chip, Grid, Stack, Tab, Tabs, Typography } from '@mui/material';
import { useEffect, useState } from 'react';
import { bffApi, TARGET_LABELS, type ActionEntry, type MessageEntry, type Target, TARGETS } from '../services/bffApi';

const LEVEL_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  info:  'success',
  warn:  'warning',
  error: 'error',
};

const dirIcon = (dir: string) =>
  dir === 'recv'
    ? <ArrowDownwardIcon sx={{ fontSize: 12, color: '#4CAF50' }} />
    : dir === 'send'
    ? <ArrowUpwardIcon sx={{ fontSize: 12, color: '#1A73E8' }} />
    : null;

// ── Action log ────────────────────────────────────────────────────────────────

function ActionsPanel({ target }: { target: Target | null }) {
  const [actions,  setActions]  = useState<ActionEntry[]>([]);
  const [loading,  setLoading]  = useState(false);

  const load = async () => {
    setLoading(true);
    try { setActions(await bffApi.actions(target ?? undefined)); }
    catch { /* ignore */ }
    finally { setLoading(false); }
  };

  useEffect(() => { void load(); }, [target]);

  return (
    <Card>
      <CardContent sx={{ p: '20px 24px !important' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
          <Box>
            <Typography variant="h6" sx={{ mb: 0.25 }}>Action log</Typography>
            <Typography variant="body2">{actions.length} entries</Typography>
          </Box>
          <Button size="small" startIcon={<RefreshIcon />} onClick={load} disabled={loading}>
            Refresh
          </Button>
        </Box>
        <Box sx={{ maxHeight: 440, overflow: 'auto' }}>
          <Stack spacing={0.75}>
            {actions.length === 0 && (
              <Typography variant="body2">No actions yet.</Typography>
            )}
            {[...actions].reverse().map((a) => (
              <Box key={a.id} sx={{
                p: 1.5, borderRadius: 2,
                border: '1px solid rgba(0,0,0,.06)',
                bgcolor: a.level === 'error' ? 'rgba(244,67,53,.04)' : '#fafafa',
              }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.25, flexWrap: 'wrap' }}>
                  <Chip
                    label={a.target}
                    size="small"
                    color={a.target === 'rti-so' ? 'success' : 'info'}
                    sx={{ fontSize: '0.6rem', height: 18 }}
                  />
                  <Chip
                    label={a.status}
                    size="small"
                    color={LEVEL_COLOR[a.level] ?? 'default'}
                    sx={{ fontSize: '0.6rem', height: 18 }}
                  />
                  <Typography sx={{ fontWeight: 700, color: '#344767', fontSize: '0.8rem', flexGrow: 1 }}>
                    {a.message}
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#7b809a', textTransform: 'none', letterSpacing: 0, whiteSpace: 'nowrap' }}>
                    {a.time}{a.duration_ms !== null ? ` (${a.duration_ms} ms)` : ''}
                  </Typography>
                </Box>
              </Box>
            ))}
          </Stack>
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Message log ───────────────────────────────────────────────────────────────

function MessagesPanel({ target }: { target: Target | null }) {
  const [msgs,    setMsgs]    = useState<MessageEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try { setMsgs(await bffApi.messages(target ?? undefined)); }
    catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const clear = async () => {
    await bffApi.clearMessages(target ?? undefined);
    setMsgs([]);
  };

  useEffect(() => { void load(); }, [target]);

  return (
    <Card>
      <CardContent sx={{ p: '20px 24px !important' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
          <Box>
            <Typography variant="h6" sx={{ mb: 0.25 }}>WebSocket frames</Typography>
            <Typography variant="body2">{msgs.length} frames</Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button size="small" startIcon={<RefreshIcon />} onClick={load} disabled={loading}>Refresh</Button>
            <Button size="small" color="error" variant="outlined" onClick={clear}>Clear</Button>
          </Stack>
        </Box>
        <Box sx={{ maxHeight: 440, overflow: 'auto' }}>
          <Stack spacing={0.75}>
            {msgs.length === 0 && (
              <Typography variant="body2">No frames yet.</Typography>
            )}
            {[...msgs].reverse().map((m) => (
              <Box key={m.id} sx={{ p: 1.5, borderRadius: 2, border: '1px solid rgba(0,0,0,.08)', bgcolor: '#fafafa' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5, flexWrap: 'wrap' }}>
                  {dirIcon(m.direction)}
                  <Chip label={m.target} size="small"
                    color={m.target === 'rti-so' ? 'success' : 'info'}
                    sx={{ fontSize: '0.6rem', height: 18 }} />
                  <Typography sx={{ fontWeight: 700, color: '#344767', fontSize: '0.8rem', flexGrow: 1 }}>
                    {m.service_type}
                  </Typography>
                  <Chip label={m.direction} size="small"
                    color={m.direction === 'recv' ? 'success' : m.direction === 'send' ? 'info' : 'default'}
                    sx={{ fontSize: '0.6rem' }} />
                  <Typography variant="caption" sx={{ color: '#7b809a', textTransform: 'none', letterSpacing: 0 }}>
                    {m.timestamp}
                  </Typography>
                </Box>
                <pre style={{ margin: 0, fontSize: '0.7rem', color: '#7b809a', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {m.preview}
                </pre>
              </Box>
            ))}
          </Stack>
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function DiagnosticsPage() {
  const [tab, setTab] = useState<Target | 'all'>('all');
  const target: Target | null = tab === 'all' ? null : tab;

  return (
    <Box>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab value="all" label="All targets" />
        {TARGETS.map((t) => <Tab key={t} value={t} label={TARGET_LABELS[t]} />)}
      </Tabs>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, lg: 6 }}>
          <ActionsPanel target={target} />
        </Grid>
        <Grid size={{ xs: 12, lg: 6 }}>
          <MessagesPanel target={target} />
        </Grid>
      </Grid>
    </Box>
  );
}
