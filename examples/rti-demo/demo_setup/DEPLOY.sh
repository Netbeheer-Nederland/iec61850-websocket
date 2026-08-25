#!/bin/bash
# RTI Demo Deployment Script
# This script provides quick deployment commands for each device

echo "RTI Demo Setup - Deployment Guide"
echo "================================"
echo ""

case "$1" in
    hmi|HMI|pc|PC)
        echo "Deploying HMI + BFF on PC..."
        echo "Command: docker-compose -f docker-compose.HMI.yml up -d --build"
        echo ""
        echo "Before running, edit docker-compose.HMI.yml:"
        echo "  - Set REACT_APP_BFF_URL=http://<PC_IP>:5000"
        echo ""
        docker-compose -f docker-compose.HMI.yml up -d --build
        ;;
    fsp|FSP|rpi1|RPI1)
        echo "Deploying FSP + IO Server on Raspberry Pi 1..."
        echo "Command: docker-compose -f docker-compose.FSP.yml up -d --build"
        echo ""
        docker-compose -f docker-compose.FSP.yml up -d --build
        ;;
    so|SO|rpi2|RPI2)
        echo "Deploying SO + IO Server on Raspberry Pi 2..."
        echo "Command: docker-compose -f docker-compose.SO.yml up -d --build"
        echo ""
        docker-compose -f docker-compose.SO.yml up -d --build
        ;;
    down|stop|STOP)
        echo "Stopping all services on this device..."
        docker-compose -f docker-compose.HMI.yml down 2>/dev/null
        docker-compose -f docker-compose.FSP.yml down 2>/dev/null
        docker-compose -f docker-compose.SO.yml down 2>/dev/null
        echo "All services stopped"
        ;;
    logs|LOG|log)
        echo "Usage: ./DEPLOY.sh logs <service>"
        echo "Example: ./DEPLOY.sh logs hmi"
        if [ -n "$2" ]; then
            docker-compose -f docker-compose.$2.yml logs -f
        else
            echo "Please specify: hmi, fsp, or so"
        fi
        ;;
    *)
        echo "RTI Demo Setup - Usage"
        echo "====================="
        echo ""
        echo "Deploy on specific device:"
        echo "  ./DEPLOY.sh hmi      # Deploy HMI+BFF on PC"
        echo "  ./DEPLOY.sh fsp      # Deploy FSP+IO on Raspberry Pi 1"
        echo "  ./DEPLOY.sh so       # Deploy SO+IO on Raspberry Pi 2"
        echo ""
        echo "Management commands:"
        echo "  ./DEPLOY.sh stop     # Stop all services"
        echo "  ./DEPLOY.sh logs hmi  # View HMI logs"
        echo "  ./DEPLOY.sh logs fsp  # View FSP logs"
        echo "  ./DEPLOY.sh logs so   # View SO logs"
        echo ""
        echo "Manual deployment (without this script):"
        echo "  cd examples/rti-demo/demo_setup"
        echo "  docker-compose -f docker-compose.HMI.yml up -d --build"
        echo "  docker-compose -f docker-compose.FSP.yml up -d --build"
        echo "  docker-compose -f docker-compose.SO.yml up -d --build"
        ;;
esac
