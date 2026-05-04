import React from 'react';
import ReactDOM from 'react-dom/client';
import { CssBaseline } from '@mui/material';
import { ThemeProvider } from './app/providers/ThemeProvider';
import { AppRouter } from './app/router/AppRouter';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <CssBaseline />
      <AppRouter />
    </ThemeProvider>
  </React.StrictMode>,
);
