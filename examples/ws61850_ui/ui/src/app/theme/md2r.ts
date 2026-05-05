import { createTheme } from '@mui/material/styles';

export const md2rTheme = createTheme({
  palette: {
    mode: 'light',
    primary:    { main: '#e91e63', light: '#ec407a',  dark: '#c2185b' },
    info:       { main: '#1A73E8', light: '#49a3f1',  dark: '#1565c0' },
    success:    { main: '#4CAF50', light: '#66BB6A',  dark: '#388E3C' },
    warning:    { main: '#fb8c00', light: '#FFA726',  dark: '#e65100' },
    error:      { main: '#F44335', light: '#EF5350',  dark: '#e53935' },
    background: { default: '#f0f2f5', paper: '#ffffff' },
    text:       { primary: '#344767', secondary: '#7b809a' },
  },

  shape: { borderRadius: 12 },

  typography: {
    fontFamily: '"Roboto","Helvetica","Arial",sans-serif',
    h4: { fontWeight: 700, fontSize: '1.5rem',  color: '#344767' },
    h5: { fontWeight: 700, fontSize: '1.25rem', color: '#344767' },
    h6: { fontWeight: 700, fontSize: '1rem',    color: '#344767' },
    body1: { fontSize: '0.875rem', color: '#7b809a' },
    body2: { fontSize: '0.75rem',  color: '#7b809a' },
    caption: {
      fontSize: '0.65rem',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      color: '#7b809a',
    },
  },

  components: {
    MuiCssBaseline: {
      styleOverrides: {
        body: { backgroundColor: '#f0f2f5' },
      },
    },

    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          boxShadow: '0 2px 12px 0 rgba(0,0,0,.16)',
          overflow: 'visible',
        },
      },
    },

    MuiPaper: {
      styleOverrides: {
        root: ({ ownerState }) =>
          ownerState.variant === 'outlined'
            ? { borderRadius: 12, boxShadow: 'none' }
            : { borderRadius: 16, boxShadow: '0 2px 12px 0 rgba(0,0,0,.10)' },
      },
    },

    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          textTransform: 'none',
          fontWeight: 700,
          fontSize: '0.75rem',
        },
        containedPrimary:  { background: 'linear-gradient(195deg,#EC407A,#D81B60)', boxShadow: '0 3px 3px -2px rgba(233,30,99,.4)' },
        containedInfo:     { background: 'linear-gradient(195deg,#49a3f1,#1A73E8)', boxShadow: '0 3px 3px -2px rgba(26,115,232,.4)' },
        containedSuccess:  { background: 'linear-gradient(195deg,#66BB6A,#43A047)', boxShadow: '0 3px 3px -2px rgba(76,175,80,.4)' },
        containedWarning:  { background: 'linear-gradient(195deg,#FFA726,#FB8C00)', boxShadow: '0 3px 3px -2px rgba(251,140,0,.4)' },
        containedError:    { background: 'linear-gradient(195deg,#EF5350,#E53935)', boxShadow: '0 3px 3px -2px rgba(244,67,53,.4)' },
      },
    },

    MuiChip: {
      styleOverrides: {
        root: { fontSize: '0.65rem', fontWeight: 700, borderRadius: 8 },
      },
    },

    MuiTableHead: {
      styleOverrides: {
        root: {
          '& .MuiTableCell-root': {
            fontWeight: 700,
            fontSize: '0.65rem',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            color: '#7b809a',
            paddingTop: 12,
            paddingBottom: 12,
            borderBottom: '1px solid rgba(0,0,0,.08)',
          },
        },
      },
    },

    MuiTableBody: {
      styleOverrides: {
        root: {
          '& .MuiTableRow-root:last-child .MuiTableCell-root': {
            borderBottom: 'none',
          },
        },
      },
    },

    MuiTextField: {
      defaultProps: { variant: 'outlined', size: 'small' },
    },

    MuiDivider: {
      styleOverrides: {
        root: { borderColor: 'rgba(0,0,0,.08)' },
      },
    },
  },
});

export const gradients = {
  dark:    'linear-gradient(195deg,#42424a,#191919)',
  primary: 'linear-gradient(195deg,#EC407A,#D81B60)',
  info:    'linear-gradient(195deg,#49a3f1,#1A73E8)',
  success: 'linear-gradient(195deg,#66BB6A,#43A047)',
  warning: 'linear-gradient(195deg,#FFA726,#FB8C00)',
  error:   'linear-gradient(195deg,#EF5350,#E53935)',
} as const;

export type GradientKey = keyof typeof gradients;
