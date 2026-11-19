#!/bin/bash
set -e
cd /mnt/d/Job/Projects/linkedin-ai-agent/backend

echo "===== Classes containing 'job' ====="
grep -o 'class="[^"]*job[^"]*"' dom_snapshot.html | sort -u | head -80

echo ""
echo "===== Classes containing 'scaffold' ====="
grep -o 'class="[^"]*scaffold[^"]*"' dom_snapshot.html | sort -u | head -40

echo ""
echo "===== Classes containing 'search-result' ====="
grep -o 'class="[^"]*search-result[^"]*"' dom_snapshot.html | sort -u | head -40

echo ""
echo "===== data-* attributes on li elements ====="
grep -o '<li [^>]*data-[^>]*>' dom_snapshot.html | head -30

echo ""
echo "===== All anchor hrefs containing jobs/view ====="
grep -o 'href="[^"]*jobs/view[^"]*"' dom_snapshot.html | head -30

echo ""
echo "===== All anchor hrefs containing currentJobId ====="
grep -o 'href="[^"]*currentJobId[^"]*"' dom_snapshot.html | head -20

echo ""
echo "===== Tags with data-entity-urn ====="
grep -o '<[a-z]* [^>]*data-entity-urn[^>]*>' dom_snapshot.html | head -20

echo ""
echo "===== Tags with data-job ====="
grep -o '<[a-z]* [^>]*data-job[^>]*>' dom_snapshot.html | head -20

echo ""
echo "===== Unique li class values ====="
grep -o '<li class="[^"]*"' dom_snapshot.html | sort -u | head -40

echo ""
echo "===== Script tags (SPA data) ====="
grep -c '<script' dom_snapshot.html

echo ""
echo "===== Page title ====="
grep -o '<title>[^<]*</title>' dom_snapshot.html
