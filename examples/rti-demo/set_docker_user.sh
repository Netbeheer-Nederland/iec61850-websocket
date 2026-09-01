#!/bin/bash
# set_docker_user.sh - Set Docker build variables for demo_io (rti-io) container
#
# Detects UID, GID, and group IDs for a given user and exports them as
# environment variables for Docker Compose to use when building the rti-io container.
#
# Usage:
#   ./set_docker_user.sh [username]
#   Default username: pi
#
# Example:
#   ./set_docker_user.sh pi && docker-compose up --build
#   ./set_docker_user.sh myuser && docker-compose up --build

set -e

# Use first argument as username, default to "pi"
USERNAME=${1:-pi}

echo "Detecting host info for user: $USERNAME"

# Get user UID and GID
PI_USER=$USERNAME
PI_UID=$(id -u "$USERNAME" 2>/dev/null || echo "1000")
PI_GID=$(id -g "$USERNAME" 2>/dev/null || echo "1000")

# Get hardware group IDs (fall back to Raspberry Pi defaults)
GPIO_GID=$(getent group gpio | cut -d: -f3 2>/dev/null || echo "986")
I2C_GID=$(getent group i2c | cut -d: -f3 2>/dev/null || echo "988")
SPI_GID=$(getent group spi | cut -d: -f3 2>/dev/null || echo "989")

# Export variables for Docker Compose
export PI_USER=$PI_USER
export PI_UID=$PI_UID
export PI_GID=$PI_GID
export GPIO_GID=$GPIO_GID
export I2C_GID=$I2C_GID
export SPI_GID=$SPI_GID

echo "Configuration for Docker build:"
echo "  User:  $PI_USER (UID=$PI_UID, GID=$PI_GID)"
echo "  Groups: gpio=$GPIO_GID, i2c=$I2C_GID, spi=$SPI_GID"
echo ""
echo "Now run: docker-compose up --build"
