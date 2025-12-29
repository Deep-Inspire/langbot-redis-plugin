#!/bin/bash
# Monitor plugin logs in real-time

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"

# Create logs directory if not exists
mkdir -p "$LOG_DIR"

# Get today's log file
LOG_FILE="$LOG_DIR/wecom_redis_plugin_$(date +%Y%m%d).log"

echo "Monitoring plugin logs: $LOG_FILE"
echo "Press Ctrl+C to stop"
echo "----------------------------------------"

# Create empty log file if not exists
touch "$LOG_FILE"

# Tail the log file
tail -f "$LOG_FILE"
