#!/bin/bash
# RTI Demo Launcher for WSL
# This script provides a simple way to launch services in WSL

# Get the Windows host IP for WSL networking
WIN_HOST_IP=$(grep nameserver /etc/resolv.conf | awk '{print $2}')

if [ -z "$WIN_HOST_IP" ]; then
    echo "Error: Could not determine Windows host IP"
    echo "Make sure WSL networking is properly configured"
    exit 1
fi

echo "Windows Host IP: $WIN_HOST_IP"
echo "Starting RTI Demo Services..."
echo "Access services using: http://$WIN_HOST_IP:PORT"
echo ""

# Launch BFF Server
python3 bff/bff_server.py &
echo "BFF Server started on port 5000 - http://$WIN_HOST_IP:5000"

# Launch FSP ACSI-Server_WebsocketActive  
python3 fsp/bff_endpoint.py &
echo "FSP ACSI-Server_WebsocketActive started on port 5001 - http://$WIN_HOST_IP:5001"

# Launch SO ACSI-Client_WebsocketPassive
python3 so/bff_endpoint.py &
echo "SO ACSI-Client_WebsocketPassive started on port 5002 - http://$WIN_HOST_IP:5002"

# Launch Frontend (simple HTTP server)
cd front-end
python3 -m http.server 8080 &
cd ..
echo "Frontend started on port 8080 - http://$WIN_HOST_IP:8080"

echo ""
echo "All services are running in background."
echo "To stop all services: pkill -f python3"
echo "To check running processes: ps aux | grep python3"
echo ""
echo "Test URLs:"
echo "  BFF Health:     http://$WIN_HOST_IP:5000/api/health"
echo "  FSP Docs:       http://$WIN_HOST_IP:5001/api/docs"
echo "  SO Status:      http://$WIN_HOST_IP:5002/api/iec61850client/status"
echo "  Frontend:       http://$WIN_HOST_IP:8080"