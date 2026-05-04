import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import RestartAltIcon from '@mui/icons-material/RestartAlt';
import { Box, Button, Card, CardContent, Chip, Grid, Stack, Typography } from '@mui/material';
import { websocketClient } from '../services/websocketClient';
import { useScenarioStore } from '../stores/scenarioStore';
import { gradients } from '../app/theme/md2r';

const scenarioColors: Record<string, string> = {
  'quality-degrade':  gradients.warning,
  'burst-load':       gradients.info,
  'connection-loss':  gradients.error,
};

export function ScenariosPage() {
  const scenarios      = useScenarioStore((s) => s.scenarios);
  const activeScenarioId = useScenarioStore((s) => s.activeScenarioId);
  const lastState      = useScenarioStore((s) => s.lastState);
  const setActiveScenario = useScenarioStore((s) => s.setActiveScenario);

  return (
    <Box>
      <Grid container spacing={3}>
        {scenarios.map((scenario) => {
          const isActive = scenario.id === activeScenarioId;
          const gradient = scenarioColors[scenario.id] ?? gradients.dark;

          return (
            <Grid key={scenario.id} size={{ xs: 12, md: 6, lg: 4 }}>
              <Card>
                {/* Gradient header strip */}
                <Box
                  sx={{
                    height: 6,
                    background: gradient,
                    borderRadius: '16px 16px 0 0',
                  }}
                />
                <CardContent sx={{ p: '20px 24px !important' }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1 }}>
                    <Typography variant="h6">{scenario.name}</Typography>
                    {isActive && (
                      <Chip label="Running" color="success" size="small" sx={{ fontWeight: 700 }} />
                    )}
                  </Box>
                  <Typography variant="body2" sx={{ mb: 2.5, minHeight: 36 }}>
                    {scenario.description}
                  </Typography>
                  <Stack direction="row" spacing={1}>
                    <Button
                      variant="contained"
                      color="info"
                      size="small"
                      startIcon={<PlayArrowIcon />}
                      disabled={isActive}
                      onClick={() => {
                        setActiveScenario(scenario.id);
                        websocketClient.send({ type: 'scenario.run', scenarioId: scenario.id });
                      }}
                    >
                      Run
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<RestartAltIcon />}
                      onClick={() => {
                        setActiveScenario(undefined);
                        websocketClient.send({ type: 'scenario.reset' });
                      }}
                    >
                      Reset
                    </Button>
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          );
        })}

        {/* State panel */}
        <Grid size={{ xs: 12 }}>
          <Card>
            <CardContent sx={{ p: '20px 24px !important' }}>
              <Typography variant="h6" sx={{ mb: 1.5 }}>Current state</Typography>
              <Grid container spacing={2}>
                {[
                  ['Active scenario', activeScenarioId ?? '—'],
                  ['Status',         lastState?.state ?? 'idle'],
                  ['Step',           String(lastState?.step ?? 0)],
                ].map(([label, value]) => (
                  <Grid key={label} size={{ xs: 12, sm: 4 }}>
                    <Typography variant="caption" sx={{ display: 'block', mb: 0.25 }}>{label}</Typography>
                    <Typography sx={{ color: 'text.primary', fontWeight: 700, fontSize: '0.875rem' }}>
                      {value}
                    </Typography>
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
