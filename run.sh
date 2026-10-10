#!/bin/bash
# Start Aurora:  ./run.sh      (foreground; Ctrl+C or ESC on the face window to stop)
cd "$(dirname "$0")" || exit 1
mkdir -p logs; exec python3 brain.py 2>&1 | tee -a logs/aurora.log
