import {
  Box, Button, Card, CardContent, Chip, Divider, Grid,
  List, ListItemButton, ListItemText, Tab, Tabs, TextField, Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { bffApi, TARGET_LABELS, type Target } from '../services/bffApi';

interface LdEntry  { name: string; [k: string]: unknown }
interface LnEntry  { name: string; prefix?: string; lnClass?: string; [k: string]: unknown }
interface DoEntry  { name: string; cdc?: string; [k: string]: unknown }

export function ModelPage() {
  const [target,     setTarget]     = useState<Target>('rti-so');
  const [status,     setStatus]     = useState<string>('');
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  // Three-level tree: LD → LN → DO
  const [lds,        setLds]        = useState<LdEntry[]>([]);
  const [selectedLd, setSelectedLd] = useState<string | null>(null);
  const [lns,        setLns]        = useState<LnEntry[]>([]);
  const [selectedLn, setSelectedLn] = useState<string | null>(null);
  const [doDetail,   setDoDetail]   = useState<unknown>(null);

  const [search, setSearch] = useState('');

  // Load model / trigger build
  const loadModel = async () => {
    setLoading(true); setError(null); setLds([]); setLns([]); setDoDetail(null);
    setSelectedLd(null); setSelectedLn(null);
    try {
      const res = await bffApi.model(target) as { status?: string; logical_devices?: LdEntry[] };
      setStatus(res?.status ?? '');
      setLds(res?.logical_devices ?? []);
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const selectLd = async (ldName: string) => {
    setSelectedLd(ldName); setLns([]); setSelectedLn(null); setDoDetail(null);
    try {
      const res = await bffApi.listLd(ldName, target) as { logical_nodes?: LnEntry[] };
      setLns(res?.logical_nodes ?? []);
    } catch (e) { setError(String(e)); }
  };

  const selectLn = async (ldName: string, lnName: string) => {
    setSelectedLn(lnName); setDoDetail(null);
    try {
      const res = await bffApi.getLn(ldName, lnName, target);
      setDoDetail(res);
    } catch (e) { setError(String(e)); }
  };

  useEffect(() => { void loadModel(); }, [target]);

  const filteredLds = lds.filter((ld) =>
    !search || ld.name?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <Box>
      <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
        <Tabs value={target} onChange={(_, v: Target) => setTarget(v)}>
          {(['rti-so', 'rti-fsp'] as Target[]).map((t) => (
            <Tab key={t} value={t} label={TARGET_LABELS[t]} />
          ))}
        </Tabs>
        <Button variant="outlined" size="small" onClick={loadModel} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </Button>
        <Button variant="text" size="small"
          onClick={async () => { await bffApi.modelRebuild(target); void loadModel(); }}>
          Rebuild
        </Button>
        {status && (
          <Chip label={status} size="small" color={status === 'ready' ? 'success' : 'warning'} />
        )}
      </Box>

      {error && (
        <Typography variant="body2" color="error" sx={{ mb: 2 }}>{error}</Typography>
      )}

      <Grid container spacing={3}>
        {/* Logical devices */}
        <Grid size={{ xs: 12, md: 3 }}>
          <Card sx={{ height: '100%' }}>
            <CardContent sx={{ p: '16px 16px 0 !important' }}>
              <Typography variant="h6" sx={{ mb: 1, fontSize: '0.875rem' }}>Logical Devices</Typography>
              <TextField label="Search" value={search} onChange={(e) => setSearch(e.target.value)}
                fullWidth size="small" sx={{ mb: 1 }} />
            </CardContent>
            <List dense sx={{ maxHeight: 440, overflow: 'auto', px: 1, pb: 1 }}>
              {filteredLds.length === 0 && (
                <Box sx={{ px: 2, py: 1 }}>
                  <Typography variant="body2">
                    {loading ? 'Loading…' : 'No logical devices. Is the target connected?'}
                  </Typography>
                </Box>
              )}
              {filteredLds.map((ld) => (
                <ListItemButton key={ld.name} selected={ld.name === selectedLd}
                  onClick={() => void selectLd(ld.name)} sx={{ borderRadius: 1.5, mb: 0.25 }}>
                  <ListItemText primary={ld.name}
                    slotProps={{ primary: { sx: { fontSize: '0.8rem', fontWeight: 600, color: '#344767' } } }} />
                </ListItemButton>
              ))}
            </List>
          </Card>
        </Grid>

        {/* Logical nodes */}
        <Grid size={{ xs: 12, md: 3 }}>
          <Card sx={{ height: '100%' }}>
            <CardContent sx={{ p: '16px 16px 0 !important' }}>
              <Typography variant="h6" sx={{ mb: 1, fontSize: '0.875rem' }}>
                Logical Nodes {selectedLd ? `(${selectedLd})` : ''}
              </Typography>
            </CardContent>
            <List dense sx={{ maxHeight: 480, overflow: 'auto', px: 1, pb: 1 }}>
              {!selectedLd && (
                <Box sx={{ px: 2, py: 1 }}>
                  <Typography variant="body2">Select a logical device.</Typography>
                </Box>
              )}
              {lns.map((ln) => (
                <ListItemButton key={ln.name} selected={ln.name === selectedLn}
                  onClick={() => void selectLn(selectedLd!, ln.name)} sx={{ borderRadius: 1.5, mb: 0.25 }}>
                  <ListItemText primary={ln.name}
                    secondary={ln.lnClass ?? ''}
                    slotProps={{ primary: { sx: { fontSize: '0.8rem', fontWeight: 600, color: '#344767' } } }} />
                </ListItemButton>
              ))}
            </List>
          </Card>
        </Grid>

        {/* Detail */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent sx={{ p: '20px 24px !important' }}>
              <Typography variant="h6" sx={{ mb: 2 }}>
                {selectedLn ? `${selectedLd} / ${selectedLn}` : 'Details'}
              </Typography>
              {!doDetail && (
                <Typography variant="body2">Select a logical node to view its data objects.</Typography>
              )}
              {doDetail !== null && (
                <>
                  <Divider sx={{ mb: 1.5 }} />
                  <Box sx={{ maxHeight: 420, overflow: 'auto' }}>
                    <pre style={{ margin: 0, fontSize: '0.72rem', whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: '#344767' }}>
                      {JSON.stringify(doDetail, null, 2)}
                    </pre>
                  </Box>
                  <Divider sx={{ mt: 1.5, mb: 1 }} />
                  <Link to="/data">
                    <Typography variant="body2" sx={{ color: '#1A73E8', fontWeight: 600, cursor: 'pointer' }}>
                      Read/write data →
                    </Typography>
                  </Link>
                </>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
