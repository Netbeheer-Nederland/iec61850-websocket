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

## Notes
- The container uses Node.js 18 and serves static files with http-server.
- If you have a package.json, dependencies will be installed automatically.
