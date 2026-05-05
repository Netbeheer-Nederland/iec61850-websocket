import {
  Box, Button, Card, CardContent, Chip, Grid, MenuItem, Select, Stack,
  Tab, Tabs, TextField, Typography,
} from '@mui/material';
import { useState } from 'react';
import { bffApi, TARGET_LABELS, type Target } from '../services/bffApi';

// ── Shared result display ─────────────────────────────────────────────────────

function ResultBox({ result, error }: { result: unknown; error: string | null }) {
  if (error) return <Typography variant="body2" color="error" sx={{ fontSize: '0.75rem' }}>{error}</Typography>;
  if (result === undefined) return null;
  return (
    <Box sx={{ p: 1.5, bgcolor: '#f8f9fa', borderRadius: 2, border: '1px solid rgba(0,0,0,.06)' }}>
      <pre style={{ margin: 0, fontSize: '0.72rem', whiteSpace: 'pre-wrap', wordBreak: 'break-all', color: '#344767' }}>
        {JSON.stringify(result, null, 2)}
      </pre>
    </Box>
  );
}

// ── Read value panel ──────────────────────────────────────────────────────────

function ReadValuePanel({ target }: { target: Target }) {
  const [objRef,  setObjRef]  = useState('');
  const [fc,      setFc]      = useState('MX');
  const [result,  setResult]  = useState<unknown>(undefined);
  const [error,   setError]   = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const read = async () => {
    setLoading(true); setError(null); setResult(undefined);
    try { setResult(await bffApi.readValue(objRef, fc, target)); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const getFcs = async () => {
    if (!objRef) return;
    setLoading(true); setError(null); setResult(undefined);
    try { setResult(await bffApi.getFcs(objRef, target)); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  return (
    <Card>
      <CardContent sx={{ p: '20px 24px !important' }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Read value</Typography>
        <Stack spacing={1.5}>
          <TextField label="Object reference" value={objRef} onChange={(e) => setObjRef(e.target.value)}
            fullWidth size="small" placeholder="LD0/MMXU1.TotW.mag.f" />
          <TextField label="FC" value={fc} onChange={(e) => setFc(e.target.value)}
            fullWidth size="small" placeholder="MX" />
          <Stack direction="row" spacing={1}>
            <Button variant="contained" color="info" size="small" onClick={read}
              disabled={loading || !objRef}>
              {loading ? 'Reading…' : 'Read'}
            </Button>
            <Button variant="outlined" size="small" onClick={getFcs}
              disabled={loading || !objRef}>
              Get FCs
            </Button>
          </Stack>
          <ResultBox result={result} error={error} />
        </Stack>
      </CardContent>
    </Card>
  );
}

// ── Write value panel ─────────────────────────────────────────────────────────

const DATA_TYPES = ['float', 'int', 'bool', 'string', 'quality'];

function WriteValuePanel({ target }: { target: Target }) {
  const [objRef,   setObjRef]   = useState('');
  const [fc,       setFc]       = useState('MX');
  const [value,    setValue]    = useState('');
  const [dataType, setDataType] = useState('float');
  const [result,   setResult]   = useState<unknown>(undefined);
  const [error,    setError]    = useState<string | null>(null);
  const [loading,  setLoading]  = useState(false);

  const write = async () => {
    setLoading(true); setError(null); setResult(undefined);
    let parsed: unknown = value;
    if (dataType === 'float') parsed = parseFloat(value);
    else if (dataType === 'int') parsed = parseInt(value, 10);
    else if (dataType === 'bool') parsed = value === 'true' || value === '1';
    try { setResult(await bffApi.writeValue(objRef, fc, parsed, dataType, target)); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  return (
    <Card>
      <CardContent sx={{ p: '20px 24px !important' }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Write value</Typography>
        <Stack spacing={1.5}>
          <TextField label="Object reference" value={objRef} onChange={(e) => setObjRef(e.target.value)}
            fullWidth size="small" placeholder="LD0/MMXU1.TotW.mag.f" />
          <Stack direction="row" spacing={1.5}>
            <TextField label="FC" value={fc} onChange={(e) => setFc(e.target.value)}
              fullWidth size="small" placeholder="MX" />
            <Select value={dataType} onChange={(e) => setDataType(e.target.value)}
              size="small" sx={{ minWidth: 100 }}>
              {DATA_TYPES.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
            </Select>
          </Stack>
          <TextField label="Value" value={value} onChange={(e) => setValue(e.target.value)}
            fullWidth size="small" />
          <Button variant="contained" color="warning" size="small" onClick={write}
            disabled={loading || !objRef || !value}>
            {loading ? 'Writing…' : 'Write'}
          </Button>
          <ResultBox result={result} error={error} />
        </Stack>
      </CardContent>
    </Card>
  );
}

// ── RCB panel ─────────────────────────────────────────────────────────────────

function RcbPanel({ target }: { target: Target }) {
  const [rcbRef,  setRcbRef]  = useState('');
  const [rcbType, setRcbType] = useState<'URCB' | 'BRCB'>('URCB');
  const [result,  setResult]  = useState<unknown>(undefined);
  const [error,   setError]   = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const getValues = async () => {
    setLoading(true); setError(null); setResult(undefined);
    try { setResult(await bffApi.rcbValues(rcbRef, rcbType, target)); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const enableReporting = async () => {
    setLoading(true); setError(null); setResult(undefined);
    try { setResult(await bffApi.rcbSet(rcbRef, rcbType, { RptEna: true }, target)); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  const disableReporting = async () => {
    setLoading(true); setError(null); setResult(undefined);
    try { setResult(await bffApi.rcbSet(rcbRef, rcbType, { RptEna: false }, target)); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  return (
    <Card>
      <CardContent sx={{ p: '20px 24px !important' }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Report control block</Typography>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1.5}>
            <TextField label="RCB reference" value={rcbRef} onChange={(e) => setRcbRef(e.target.value)}
              fullWidth size="small" placeholder="LD0/LLN0.RP.urcb01" />
            <Select value={rcbType} onChange={(e) => setRcbType(e.target.value as 'URCB' | 'BRCB')}
              size="small" sx={{ minWidth: 90 }}>
              <MenuItem value="URCB">URCB</MenuItem>
              <MenuItem value="BRCB">BRCB</MenuItem>
            </Select>
          </Stack>
          <Stack direction="row" spacing={1} flexWrap="wrap">
            <Button variant="outlined" size="small" onClick={getValues}
              disabled={loading || !rcbRef}>
              Get values
            </Button>
            <Button variant="contained" color="success" size="small" onClick={enableReporting}
              disabled={loading || !rcbRef}>
              Enable reporting
            </Button>
            <Button variant="outlined" color="warning" size="small" onClick={disableReporting}
              disabled={loading || !rcbRef}>
              Disable
            </Button>
          </Stack>
          <ResultBox result={result} error={error} />
        </Stack>
      </CardContent>
    </Card>
  );
}

// ── Control (SBO) panel ───────────────────────────────────────────────────────

function ControlPanel({ target }: { target: Target }) {
  const [objRef,  setObjRef]  = useState('');
  const [ctlVal,  setCtlVal]  = useState('true');
  const [ctlNum,  setCtlNum]  = useState('1');
  const [result,  setResult]  = useState<unknown>(undefined);
  const [error,   setError]   = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async (action: 'select' | 'operate' | 'cancel') => {
    setLoading(true); setError(null); setResult(undefined);
    try {
      if (action === 'select')  setResult(await bffApi.controlSelect(objRef, target));
      if (action === 'operate') setResult(await bffApi.controlOperate(objRef, ctlVal === 'true', Number(ctlNum), target));
      if (action === 'cancel')  setResult(await bffApi.controlCancel(objRef, target));
    } catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  };

  return (
    <Card>
      <CardContent sx={{ p: '20px 24px !important' }}>
        <Typography variant="h6" sx={{ mb: 2 }}>Control (select-before-operate)</Typography>
        <Stack spacing={1.5}>
          <TextField label="Object reference" value={objRef} onChange={(e) => setObjRef(e.target.value)}
            fullWidth size="small" placeholder="LD0/CSWI1.Pos.Oper" />
          <Stack direction="row" spacing={1.5}>
            <Select value={ctlVal} onChange={(e) => setCtlVal(e.target.value)} size="small" sx={{ minWidth: 90 }}>
              <MenuItem value="true">true</MenuItem>
              <MenuItem value="false">false</MenuItem>
            </Select>
            <TextField label="ctlNum" value={ctlNum} onChange={(e) => setCtlNum(e.target.value)}
              size="small" type="number" sx={{ width: 90 }} />
          </Stack>
          <Stack direction="row" spacing={1}>
            {(['select', 'operate', 'cancel'] as const).map((a) => (
              <Button key={a} variant={a === 'operate' ? 'contained' : 'outlined'}
                color={a === 'cancel' ? 'error' : 'info'} size="small"
                onClick={() => run(a)} disabled={loading || !objRef}>
                {a.charAt(0).toUpperCase() + a.slice(1)}
              </Button>
            ))}
          </Stack>
          <ResultBox result={result} error={error} />
        </Stack>
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function DataPage() {
  const [tab, setTab] = useState<Target>('rti-so');

  return (
    <Box>
      <Box sx={{ mb: 2 }}>
        <Tabs value={tab} onChange={(_, v: Target) => setTab(v)} sx={{ mb: 0 }}>
          {(['rti-so', 'rti-fsp'] as Target[]).map((t) => (
            <Tab key={t} value={t} label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {TARGET_LABELS[t]}
                <Chip label={t} size="small" sx={{ fontSize: '0.6rem', height: 18 }} />
              </Box>
            } />
          ))}
        </Tabs>
      </Box>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <ReadValuePanel target={tab} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <WriteValuePanel target={tab} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <RcbPanel target={tab} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <ControlPanel target={tab} />
        </Grid>
      </Grid>
    </Box>
  );
}
