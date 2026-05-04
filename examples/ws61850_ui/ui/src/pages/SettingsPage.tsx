import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import { Box, Card, CardContent, Divider, FormControlLabel, Grid, Switch, Typography } from '@mui/material';
import { useStreamStore } from '../stores/streamStore';
import { useUiStore } from '../stores/uiStore';

export function SettingsPage() {
  const themeMode  = useUiStore((s) => s.themeMode);
  const toggleTheme = useUiStore((s) => s.toggleTheme);
  const bufferSize = Number(import.meta.env.VITE_EVENT_BUFFER_SIZE ?? 5000);

  return (
    <Box>
      <Grid container spacing={3}>
        {/* Appearance */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent sx={{ p: '20px 24px !important' }}>
              <Typography variant="h6" sx={{ mb: 0.5 }}>Appearance</Typography>
              <Typography variant="body2" sx={{ mb: 2.5 }}>
                Visual preferences for the dashboard.
              </Typography>

              <FormControlLabel
                control={
                  <Switch
                    checked={themeMode === 'dark'}
                    onChange={toggleTheme}
                    color="info"
                  />
                }
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {themeMode === 'dark'
                      ? <DarkModeIcon sx={{ fontSize: 18, color: '#7b809a' }} />
                      : <LightModeIcon sx={{ fontSize: 18, color: '#fb8c00' }} />
                    }
                    <Typography variant="body1" sx={{ color: 'text.primary' }}>
                      {themeMode === 'dark' ? 'Dark mode' : 'Light mode'}
                    </Typography>
                  </Box>
                }
              />
            </CardContent>
          </Card>
        </Grid>

        {/* Stream settings */}
        <Grid size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent sx={{ p: '20px 24px !important' }}>
              <Typography variant="h6" sx={{ mb: 0.5 }}>Event buffer</Typography>
              <Typography variant="body2" sx={{ mb: 2.5 }}>
                Ring buffer settings for the live stream.
              </Typography>

              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                <Box>
                  <Typography variant="caption" sx={{ display: 'block', mb: 0.25 }}>Buffer size</Typography>
                  <Typography sx={{ color: 'text.primary', fontWeight: 700, fontSize: '0.875rem' }}>
                    {bufferSize.toLocaleString()} events
                  </Typography>
                  <Typography variant="caption" sx={{ textTransform: 'none', letterSpacing: 0, color: '#7b809a' }}>
                    Set via VITE_EVENT_BUFFER_SIZE at build time
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* About */}
        <Grid size={{ xs: 12 }}>
          <Card>
            <CardContent sx={{ p: '20px 24px !important' }}>
              <Typography variant="h6" sx={{ mb: 1.5 }}>About</Typography>
              <Divider sx={{ mb: 2 }} />
              <Grid container spacing={2}>
                {[
                  ['Application',  'IEC 61850 RTI Demo UI'],
                  ['Stack',        'React 19 · MUI 7 · Vite 8 · Zustand 5'],
                  ['Protocol',     'IEC 61850 over WebSocket (ws61850)'],
                  ['Design',       'Material Dashboard 2 React — Creative Tim'],
                ].map(([label, value]) => (
                  <Grid key={label} size={{ xs: 12, sm: 6 }}>
                    <Typography variant="caption" sx={{ display: 'block', mb: 0.25 }}>{label}</Typography>
                    <Typography sx={{ color: 'text.primary', fontSize: '0.8rem' }}>{value}</Typography>
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
