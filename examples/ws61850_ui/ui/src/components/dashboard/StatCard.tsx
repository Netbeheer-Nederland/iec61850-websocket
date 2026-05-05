import { Box, Card, CardContent, Divider, Typography } from '@mui/material';
import type { ReactNode } from 'react';
import { gradients, type GradientKey } from '../../app/theme/md2r';

interface StatCardProps {
  label: string;
  value: ReactNode;
  icon: ReactNode;
  color?: GradientKey;
  footer?: ReactNode;
}

export function StatCard({ label, value, icon, color = 'info', footer }: StatCardProps) {
  const gradient = gradients[color];
  const shadowColor: Record<GradientKey, string> = {
    dark:    'rgba(52,71,103,.4)',
    primary: 'rgba(233,30,99,.4)',
    info:    'rgba(26,115,232,.4)',
    success: 'rgba(76,175,80,.4)',
    warning: 'rgba(251,140,0,.4)',
    error:   'rgba(244,67,53,.4)',
  };

  return (
    <Card>
      <CardContent sx={{ p: '12px 16px 0 !important' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <Box
            sx={{
              mt: -5,
              width: 64,
              height: 64,
              borderRadius: 3,
              background: gradient,
              boxShadow: `0 4px 20px 0 rgba(0,0,0,.14), 0 7px 10px -5px ${shadowColor[color]}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              flexShrink: 0,
              '& svg': { fontSize: 28 },
            }}
          >
            {icon}
          </Box>
          <Box sx={{ textAlign: 'right', py: 0.5 }}>
            <Typography variant="caption" sx={{ display: 'block', mb: 0.5 }}>
              {label}
            </Typography>
            <Typography variant="h5" sx={{ color: 'text.primary', lineHeight: 1 }}>
              {value}
            </Typography>
          </Box>
        </Box>
      </CardContent>

      {footer && (
        <>
          <Divider sx={{ mx: 2, mt: 1.5 }} />
          <Box sx={{ px: 2, pb: 1.5, pt: 1 }}>
            <Typography variant="caption" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              {footer}
            </Typography>
          </Box>
        </>
      )}
      {!footer && <Box sx={{ pb: 1.5 }} />}
    </Card>
  );
}
