#!/bin/bash
# Analyse the flagship-web RSC response content
cd /mnt/d/Job/Projects/linkedin-ai-agent/backend

echo "=== Checking all_api_responses.json ==="
if [ -f all_api_responses.json ]; then
    python3 -c "
import json, sys
data = json.load(open('all_api_responses.json'))
print(f'Total responses: {len(data)}')
for r in data:
    print(r['url'][:120])
" 2>&1
else
    echo "File not found yet"
fi
