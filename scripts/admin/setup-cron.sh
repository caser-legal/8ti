#!/bin/bash
set -e
# Setup cron job to run every 10 minutes
# The Python script will handle business hours checking

# Make scripts executable
chmod +x ../scripts/run-scheduled-scan.sh

# Add cron job (runs every 10 minutes)
SCRIPT_PATH="$(cd .. && pwd)/scripts/run-scheduled-scan.sh"
CRON_JOB="*/10 * * * * $SCRIPT_PATH"

# Check if cron job already exists
if ! crontab -l 2>/dev/null | grep -q "$SCRIPT_PATH"; then
    # Add the cron job
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Cron job added: $CRON_JOB"
else
    echo "Cron job already exists for $SCRIPT_PATH"
fi

echo "Current crontab:"
crontab -l