# RTI Demo Frontend Docker Instructions

This folder contains the frontend static web application.

## Build the Docker Image

From this directory:

```bash
docker build -t rti-demo-frontend .
```

## Run the Frontend Container

```bash
docker run --rm -p 8080:8080 rti-demo-frontend
```

The frontend will be available at: http://localhost:8080

## Run Without Docker

### Option 1: Using Node.js http-server
If you have Node.js installed:

```bash
npx http-server . -p 8080
```

The frontend will be available at: http://localhost:8080

### Option 2: Using Python
If you have Python installed:

```bash
# Python 3.x
python -m http.server 8080

# Python 2.x
python -m SimpleHTTPServer 8080
```

The frontend will be available at: http://localhost:8080

### Option 3: Using VS Code Live Server
If you have VS Code with the Live Server extension:
1. Right-click on `index.html`
2. Select "Open with Live Server"
3. The browser will open automatically (typically at http://localhost:5500 or http://127.0.0.1:5500)

## Notes
- The container uses Node.js 18 and serves static files with http-server.
- If you have a package.json, dependencies will be installed automatically.
- When running locally without Docker, make sure your backend services are accessible at the expected endpoints.
