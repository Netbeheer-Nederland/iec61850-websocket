# RTI HMI - React Frontend

This is the React-based HMI (Human Machine Interface) for the IEC 61850 RTI Demo application, converted from the original vanilla JavaScript frontend.

## Project Structure

```
hmi/
├── src/
│   ├── assets/
│   │   └── styles.css          # Original styles preserved
│   ├── components/
│   │   ├── Header.jsx
│   │   └── Sidebar.jsx
│   ├── pages/
│   │   ├── ACSIClient.jsx
│   │   ├── ACSIServer.jsx
│   │   ├── Connections.jsx
│   │   ├── Data.jsx
│   │   ├── Diagnostics.jsx
│   │   ├── Model.jsx
│   │   ├── Monitoring.jsx
│   │   ├── Reports.jsx
│   │   ├── Settings.jsx
│   │   └── Tools.jsx
│   ├── App.jsx              # Main app with routing
│   ├── index.css            # Global styles
│   └── main.jsx             # React entry point
├── package.json
├── vite.config.js
└── index.html
```

## Features

- **React 18** with functional components and hooks
- **React Router** for SPA navigation
- **Vite** for fast development and building
- **Preserved styling** from the original frontend
- **State management** using React context and useState/useEffect hooks
- **Responsive design** maintained from the original

## Available Scripts

### `npm run dev`
Runs the app in development mode. Open [http://localhost:3000](http://localhost:3000) to view it in the browser.

### `npm run build`
Builds the app for production to the `dist` folder.

### `npm run preview`
Serves the production build locally for testing.

## Installation

```bash
# Navigate to the hmi folder
cd path/to/rti-demo/hmi

# Install dependencies
npm install

# Start development server
npm run dev
```

## Key Differences from Original

1. **Component-based**: Each page is now a separate React component
2. **Declarative rendering**: No more manual DOM manipulation
3. **Client-side routing**: Uses React Router instead of manual page switching
4. **State management**: Uses React hooks (useState, useEffect) instead of DOM references
5. **ES6 modules**: Uses modern JavaScript imports/exports

## Integration Notes

- The frontend communicates with the BFF (Backend For Frontend) server on the configured port
- API endpoints are configurable via the Settings page
- Connection management uses localStorage for persistence
- All the original styling and UI elements have been preserved

## API Dependencies

The React frontend expects the following API endpoints from the BFF:
- `GET /api/health` - BFF health check
- `GET /api/endpoints` - List of active endpoints
- Various other endpoints for data reading/writing, model access, etc.

These would need to be implemented in the backend services.

## Browser Support

- Chrome (recommended)
- Firefox
- Edge
- Safari (latest versions)

The app uses modern JavaScript features and requires a recent browser.
