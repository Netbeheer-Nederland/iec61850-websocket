# RTI Demo BFF Docker Instructions

This folder contains the Backend-For-Frontend (BFF) Flask server.

## Build the Docker Image

From this directory:

```bash
docker build -t rti-demo-bff .
```

## Run the BFF Container

```bash
docker run --rm -p 5000:5000 rti-demo-bff
```

The BFF API will be available at: http://localhost:5000

## Notes
- The container uses Python 3.11 and installs dependencies from requirements.txt.
- The entrypoint is `python bff_server.py`.
