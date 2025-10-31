#!/bin/bash

# Bjorn Update Script
# This script safely updates Bjorn while preserving configurations and data
# Author: infinition
# Version: 1.0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BJORN_PATH="/home/bjorn/Bjorn"

echo -e "${BLUE}Bjorn Update Script${NC}"
echo -e "${YELLOW}This will update Bjorn while preserving your data and configurations.${NC}"

# Check if we're in the right directory
if [ ! -d "$BJORN_PATH" ]; then
    echo -e "${RED}Error: Bjorn directory not found at $BJORN_PATH${NC}"
    exit 1
fi

if [ ! -d "$BJORN_PATH/.git" ]; then
    echo -e "${RED}Error: This is not a git repository. Cannot update.${NC}"
    echo -e "${YELLOW}Please reinstall Bjorn using the installation script.${NC}"
    exit 1
fi

cd "$BJORN_PATH"

# Check if script is run as root
if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}This script must be run as root. Please use 'sudo'.${NC}"
    exit 1
fi

echo -e "\n${BLUE}Step 1: Stopping Bjorn service...${NC}"
systemctl stop bjorn.service

echo -e "${BLUE}Step 2: Backing up local changes...${NC}"
if git diff --quiet && git diff --staged --quiet; then
    echo -e "${GREEN}No local changes to backup.${NC}"
else
    echo -e "${YELLOW}Local changes detected. Creating backup...${NC}"
    git stash push -m "Auto-backup before update $(date)"
    echo -e "${GREEN}Local changes backed up.${NC}"
fi

echo -e "${BLUE}Step 3: Fetching latest updates...${NC}"
git fetch origin

echo -e "${BLUE}Step 4: Updating to latest version...${NC}"
if git pull origin main; then
    echo -e "${GREEN}Update completed successfully!${NC}"
else
    echo -e "${RED}Update failed. Attempting to restore backup...${NC}"
    git stash pop
    echo -e "${YELLOW}Backup restored. Please check for conflicts manually.${NC}"
    exit 1
fi

echo -e "${BLUE}Step 5: Updating Python dependencies...${NC}"
pip3 install --break-system-packages -r requirements.txt --upgrade

echo -e "${BLUE}Step 6: Setting correct permissions...${NC}"
chown -R bjorn:bjorn "$BJORN_PATH"
chmod +x "$BJORN_PATH"/*.sh 2>/dev/null || true

# Ensure specific critical scripts are executable
chmod +x "$BJORN_PATH/kill_port_8000.sh" 2>/dev/null || true
chmod +x "$BJORN_PATH/update_bjorn.sh" 2>/dev/null || true

echo -e "${BLUE}Step 7: Starting Bjorn service...${NC}"
systemctl start bjorn.service

# Check if service started successfully
sleep 3
if systemctl is-active --quiet bjorn.service; then
    echo -e "${GREEN}Bjorn service started successfully!${NC}"
else
    echo -e "${RED}Warning: Bjorn service failed to start. Check logs with:${NC}"
    echo -e "${YELLOW}sudo journalctl -u bjorn.service -f${NC}"
fi

echo -e "\n${GREEN}Update completed!${NC}"
echo -e "${BLUE}To check if your local changes were backed up:${NC}"
echo -e "  git stash list"
echo -e "${BLUE}To restore your local changes if needed:${NC}"
echo -e "  git stash pop"
echo -e "${BLUE}To check service status:${NC}"
echo -e "  sudo systemctl status bjorn.service"