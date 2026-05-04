import { CssBaseline, ThemeProvider as MuiThemeProvider } from '@mui/material';
import type { PropsWithChildren } from 'react';
import { md2rTheme } from '../theme/md2r';

export function ThemeProvider({ children }: PropsWithChildren) {
  return (
    <MuiThemeProvider theme={md2rTheme}>
      <CssBaseline />
      {children}
    </MuiThemeProvider>
  );
}
