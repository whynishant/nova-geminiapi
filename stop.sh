#!/bin/bash
# Stop Aurora from another terminal (SIGTERM -> graceful shutdown: speech cancelled, arecord stopped, GPIO released)
pkill -TERM -f "python3 brain.py" && echo "stop signal sent" || echo "Aurora is not running"
sleep 2; pkill -KILL -f "python3 brain.py" 2>/dev/null; pkill -x arecord 2>/dev/null; true
