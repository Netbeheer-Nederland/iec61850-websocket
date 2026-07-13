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

## Run the BFF Without Docker

You can run the BFF directly on your machine.

From this directory in Windows PowerShell:

```powershell
python -m pip install flask flask-cors requests
$env:RTI_DOCKER_ENABLED="false"
$env:FSP_BASE_URL="http://localhost:5001"
python .\bff_server.py
```

The BFF API will be available at: http://localhost:5000

Optional quick health check:

```powershell
Invoke-RestMethod http://localhost:5000/api/health
```

## Notes
- The container uses Python 3.11 and installs dependencies from requirements.txt.
- The entrypoint is `python bff_server.py`.
- For local (non-Docker) runs, adjust `FSP_BASE_URL` if your FSP service is not on `http://localhost:5001`.
