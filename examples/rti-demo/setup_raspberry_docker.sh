#!/bin/bash

# RTI Demo - Raspberry Pi Docker Setup Script
# This script sets up Docker and Docker Compose on Raspberry Pi
# Run with: bash setup_raspberry_docker.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null && \
   ! grep -q "raspberry" /proc/cpuinfo 2>/dev/null && \
   ! uname -a | grep -q "aarch64" 2>/dev/null; then
    echo -e "${RED}Error: This script is designed for Raspberry Pi only.${NC}"
    echo "Detected system: $(uname -a)"
    exit 1
fi

echo -e "${GREEN}Detected Raspberry Pi - proceeding with setup...${NC}"

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install Docker
if ! command_exists docker; then
    echo -e "${YELLOW}Installing Docker...${NC}"
    
    # Remove old versions
    sudo apt remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true
    
    # Install dependencies
    sudo apt update
    sudo apt install -y \
        ca-certificates \
        curl \
        gnupg \
        lsb-release
    
    # Add Docker's official GPG key
    sudo mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    # Set up the repository
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker
    sudo apt update
    sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    
    echo -e "${GREEN}Docker installed successfully!${NC}"
else
    echo -e "${GREEN}Docker is already installed.${NC}"
fi

# Install Docker Compose (standalone)
if ! command_exists docker-compose; then
    echo -e "${YELLOW}Installing Docker Compose...${NC}"
    
    # Install Docker Compose v2 (plugin)
    sudo apt install -y docker-compose-plugin
    
    # Also install standalone docker-compose for compatibility
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    
    echo -e "${GREEN}Docker Compose installed successfully!${NC}"
else
    echo -e "${GREEN}Docker Compose is already installed.${NC}"
fi

# Add current user to docker group
if ! groups $USER | grep -q '\bdocker\b'; then
    echo -e "${YELLOW}Adding $USER to docker group...${NC}"
    sudo usermod -aG docker $USER
    echo -e "${YELLOW}You need to log out and log back in for group changes to take effect.${NC}"
    echo -e "Or run: newgrp docker"
else
    echo -e "${GREEN}User $USER is already in docker group.${NC}"
fi

# Verify installation
echo ""
echo -e "${GREEN}Verifying Docker installation...${NC}"
docker --version
docker-compose --version 2>/dev/null || docker compose version

# Test Docker with hello-world
echo ""
echo -e "${YELLOW}Testing Docker with hello-world container...${NC}"
sudo docker run --rm hello-world

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Raspberry Pi Docker setup complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "To use Docker without sudo, please:"
echo "  1. Log out and log back in"
echo "  OR"
echo "  2. Run: newgrp docker"
echo ""
echo "To build and run the demo_IO containers:"
echo "  cd examples/rti-demo"
echo "  docker-compose build demo_io"
echo "  docker-compose up demo_io"
