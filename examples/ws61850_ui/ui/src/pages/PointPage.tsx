import { useMemo, useState } from 'react';
import {
  Box, Button, Card, CardContent, Chip, Divider,
  FormControlLabel, Grid, Stack, Switch, TextField, Typography,
} from '@mui/material';
import { useParams } from '@tanstack/react-router';
import { useModelStore } from '../stores/modelStore';
import { useStreamStore } from '../stores/streamStore';
import { useCommandStore } from '../stores/commandStore';
import { websocketClient } from '../services/websocketClient';

export function PointPage() {
  const params = useParams({ strict: false });
  const ref    = decodeURIComponent((params as { pointRef?: string }).pointRef ?? '');
  const node   = useModelStore((s) => s.refsById[ref]);
  const events = useStreamStore((s) => s.events.filter((e) => e.ref === ref).slice(-10).reverse());
  const pendingCommands = useCommandStore((s) => s.pendingCommands.filter((c) => c.ref === ref));
  const recentResults   = useCommandStore((s) => s.recentResults.filter((r) => r.ref === ref).slice(0, 5));
  const queueCommand    = useCommandStore((s) => s.queueCommand);
  const [booleanValue, setBooleanValue] = useState(true);
  const [textValue, setTextValue]       = useState('true');

  const latestEvent = events[0];
  const pending     = pendingCommands.length > 0;

  const suggestedValue = useMemo(() => {
    if (typeof latestEvent?.value === 'boolean') return booleanValue;
    if (typeof latestEvent?.value === 'number')  return Number(textValue);
    return textValue;
  }, [booleanValue, latestEvent?.value, textValue]);

  const submitCommand = () => {
    if (!node?.commandable) return;
    const commandId = `cmd-${Date.now()}`;
    const value = typeof latestEvent?.value === 'boolean' || ref.endsWith('.Oper') ? booleanValue : suggestedValue;
    queueCommand({ commandId, ref, value, timestamp: new Date().toISOString() });
    websocketClient.send({ type: 'command.request', commandId, timestamp: new Date().toISOString(), ref, value });
  };

  return (
    <Box>
      <Grid container spacing={3}>
        {/* Point info */}
        <Grid size={{ xs: 12, md: 7 }}>
          <Card>
            <CardContent sx={{ p: '20px 24px !important' }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                <Box>
                  <Typography variant="h6" sx={{ mb: 0.25 }}>Point detail</Typography>
                  <Typography variant="body2">{ref || 'No reference'}</Typography>
                </Box>
                <Chip
                  label={node?.commandable ? 'Commandable' : 'Read-only'}
                  color={node?.commandable ? 'warning' : 'default'}
                  size="small"
                />
              </Box>

              <Grid container spacing={1.5}>
                {[
                  ['Description',   node?.description ?? 'Unknown point'],
                  ['Current value', latestEvent ? String(latestEvent.value) : '—'],
                  ['Quality',       latestEvent?.quality ?? '—'],
                  ['Cause',         latestEvent?.cause ?? '—'],
                ].map(([label, value]) => (
                  <Grid key={label} size={{ xs: 12, sm: 6 }}>
                    <Typography variant="caption" sx={{ display: 'block', mb: 0.25 }}>{label}</Typography>
                    <Typography sx={{ color: 'text.primary', fontWeight: 600, fontSize: '0.8rem' }}>{value}</Typography>
                  </Grid>
                ))}
              </Grid>

              {node?.commandable && (
                <>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="h6" sx={{ mb: 1.5 }}>Command panel</Typography>
                  <Stack spacing={2}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={booleanValue}
                          onChange={(e) => setBooleanValue(e.target.checked)}
                          color="warning"
                        />
                      }
                      label={<Typography variant="body1" sx={{ color: 'text.primary' }}>Boolean value: {booleanValue ? 'true' : 'false'}</Typography>}
                    />
                    <TextField
                      label="Raw value"
                      value={textValue}
                      onChange={(e) => setTextValue(e.target.value)}
                      helperText="Used for non-boolean command types"
                      fullWidth
                    />
                    <Box>
                      <Button
                        variant="contained"
                        color="warning"
                        disabled={pending}
                        onClick={submitCommand}
                      >
                        {pending ? 'Command pending…' : 'Send command'}
                      </Button>
                    </Box>
                  </Stack>
                </>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* History + results */}
        <Grid size={{ xs: 12, md: 5 }}>
          <Stack spacing={3}>
            <Card>
              <CardContent sx={{ p: '20px 24px !important' }}>
                <Typography variant="h6" sx={{ mb: 1.5 }}>Recent history</Typography>
                {events.length === 0 ? (
                  <Typography variant="body2">No values recorded yet.</Typography>
                ) : (
                  <Stack spacing={1}>
                    {events.map((event) => (
                      <Box
                        key={`${event.timestamp}-${String(event.value)}`}
                        sx={{ p: 1.5, borderRadius: 2, border: '1px solid rgba(0,0,0,.08)', bgcolor: '#fafafa' }}
                      >
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.25 }}>
                          <Typography sx={{ color: 'text.primary', fontWeight: 700, fontSize: '0.8rem' }}>
                            {String(event.value)}
                          </Typography>
                          <Typography variant="caption" sx={{ textTransform: 'none', letterSpacing: 0, color: '#7b809a' }}>
                            {new Date(event.timestamp).toLocaleTimeString()}
                          </Typography>
                        </Box>
                        <Typography variant="caption" sx={{ textTransform: 'none', letterSpacing: 0, color: '#7b809a' }}>
                          quality: {event.quality ?? '—'} · cause: {event.cause ?? '—'}
                        </Typography>
                      </Box>
                    ))}
                  </Stack>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardContent sx={{ p: '20px 24px !important' }}>
                <Typography variant="h6" sx={{ mb: 1.5 }}>Command results</Typography>
                {recentResults.length === 0 ? (
                  <Typography variant="body2">No command responses yet.</Typography>
                ) : (
                  recentResults.map((result) => (
                    <Box
                      key={result.commandId}
                      sx={{ p: 1.5, borderRadius: 2, border: '1px solid rgba(0,0,0,.08)', bgcolor: '#fafafa', mb: 1 }}
                    >
                      <Typography sx={{ color: 'text.primary', fontWeight: 700, fontSize: '0.8rem' }}>{result.status}</Typography>
                      <Typography variant="caption" sx={{ textTransform: 'none', letterSpacing: 0, color: '#7b809a' }}>
                        {result.message ?? '—'}
                      </Typography>
                    </Box>
                  ))
                )}
              </CardContent>
            </Card>
          </Stack>
        </Grid>
      </Grid>
    </Box>
  );
}
