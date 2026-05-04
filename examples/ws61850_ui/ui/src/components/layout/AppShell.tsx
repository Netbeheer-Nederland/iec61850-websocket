import { Box, Container } from '@mui/material';
import { Outlet } from '@tanstack/react-router';
import { Navbar } from './Navbar';
import { Sidebar, SIDEBAR_WIDTH } from './Sidebar';

export function AppShell() {
  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <Sidebar />

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          ml: `${SIDEBAR_WIDTH}px`,
          pt: '60px',        // below fixed Navbar
          minHeight: '100vh',
          bgcolor: 'background.default',
        }}
      >
        <Navbar />
        <Container maxWidth={false} sx={{ py: 4, px: 3 }}>
          <Box sx={{ mt: 2 }}>
            <Outlet />
          </Box>
        </Container>
      </Box>
    </Box>
  );
}
