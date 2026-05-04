import {
  Box, Button, Card, CardContent, Chip, Stack,
  Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { TARGET_LABELS, type Target } from '../services/bffApi';
import { useReportUpdateStore } from '../stores/reportUpdateStore';

export function StreamPage() {
  const updates      = useReportUpdateStore((s) => s.updates);
  const isPolling    = useReportUpdateStore((s) => s.isPolling);
  const startPolling = useReportUpdateStore((s) => s.startPolling);
  const stopPolling  = useReportUpdateStore((s) => s.stopPolling);
  const clearUpdates = useReportUpdateStore((s) => s.clearUpdates);

  const [search,   setSearch]   = useState('');
  const [filterTgt, setFilterTgt] = useState<Target | ''>('');

  useEffect(() => {
    if (!isPolling) startPolling();
  }, [isPolling, startPolling]);

  const filtered = [...updates]
    .reverse()
    .filter((u) => {
      if (filterTgt && u.target !== filterTgt) return false;
      if (search && !u.dataRef.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });

  return (
    <Box>
      <Card>
        <CardContent sx={{ p: '20px 24px !important' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2, flexWrap: 'wrap', gap: 1 }}>
            <Box>
              <Typography variant="h6" sx={{ mb: 0.25 }}>Report updates</Typography>
              <Typography variant="body2">
                {updates.length} updates buffered · polling BFF every 2 s
              </Typography>
            </Box>
            <Stack direction="row" spacing={1}>
              <Button
                variant={isPolling ? 'outlined' : 'contained'}
                color={isPolling ? 'warning' : 'info'}
                size="small"
                onClick={() => isPolling ? stopPolling() : startPolling()}
              >
                {isPolling ? 'Pause' : 'Resume'}
              </Button>
              <Button variant="outlined" size="small" onClick={clearUpdates}>
                Clear
              </Button>
            </Stack>
          </Box>

          <Stack direction="row" spacing={1.5} sx={{ mb: 2 }}>
            <TextField
              label="Filter by reference"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              size="small"
              sx={{ flexGrow: 1 }}
            />
            <Stack direction="row" spacing={0.5}>
              {(['', 'rti-so', 'rti-fsp'] as (Target | '')[]).map((t) => (
                <Chip
                  key={t || 'all'}
                  label={t ? TARGET_LABELS[t] : 'All'}
                  size="small"
                  color={filterTgt === t ? 'info' : 'default'}
                  onClick={() => setFilterTgt(t)}
                  sx={{ cursor: 'pointer', fontWeight: filterTgt === t ? 700 : 400 }}
                />
              ))}
            </Stack>
          </Stack>

          <Box sx={{ overflow: 'auto', maxHeight: 520 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell>Timestamp</TableCell>
                  <TableCell>Target</TableCell>
                  <TableCell>Data reference</TableCell>
                  <TableCell>Values</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filtered.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4}>
                      <Typography variant="body2" sx={{ py: 2, textAlign: 'center' }}>
                        {isPolling
                          ? 'No report updates yet. Connect a target and enable reporting via Data → RCB.'
                          : 'Polling paused. Press Resume to start collecting updates.'}
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
                {filtered.map((u) => (
                  <TableRow key={u.id} hover>
                    <TableCell sx={{ whiteSpace: 'nowrap', color: '#7b809a', fontSize: '0.75rem' }}>
                      {new Date(u.timestamp * 1000).toLocaleTimeString()}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={TARGET_LABELS[u.target]}
                        size="small"
                        color={u.target === 'rti-so' ? 'success' : 'info'}
                        sx={{ fontSize: '0.65rem' }}
                      />
                    </TableCell>
                    <TableCell sx={{ fontWeight: 600, color: '#344767', fontSize: '0.8rem' }}>
                      {u.dataRef}
                    </TableCell>
                    <TableCell sx={{ color: '#7b809a', fontSize: '0.75rem', maxWidth: 320 }}>
                      <Box
                        component="span"
                        sx={{
                          display: 'block',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {JSON.stringify(u.values)}
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
