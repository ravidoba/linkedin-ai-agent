#!/bin/bash
cd /mnt/d/Job/Projects/linkedin-ai-agent/backend

echo "===== Total characters ====="
wc -c dom_snapshot.html

echo ""
echo "===== All unique data-* attribute names ====="
grep -o 'data-[a-z-]*=' dom_snapshot.html | sort -u

echo ""
echo "===== Anchors with any job-related href patterns ====="
grep -oP 'href="[^"]*"' dom_snapshot.html | grep -i 'job\|career\|position\|role' | head -40

echo ""
echo "===== All hrefs (non-asset) ====="
grep -oP 'href="https://www\.linkedin\.com[^"]*"' dom_snapshot.html | grep -v 'static\|media\|licdn\|\.css\|\.js\|\.png\|\.jpg\|\.gif\|\.svg' | sort -u | head -40

echo ""
echo "===== Inline JSON / __NEXT_DATA__ / voyager state ====="
grep -o 'window\.[A-Za-z_]*\s*=' dom_snapshot.html | sort -u | head -20
grep -o 'id="__NEXT_DATA__"' dom_snapshot.html
grep -o '"jobPostings"\|"jobs"\|"totalResultCount"\|"paginationToken"\|"entityUrn"' dom_snapshot.html | sort -u | head -20

echo ""
echo "===== jobId patterns in raw HTML ====="
grep -oP '"jobId":\s*"\d+"' dom_snapshot.html | head -20
grep -oP '"jobPostingId":\s*"\d+"' dom_snapshot.html | head -20
grep -oP '"jobsId":\s*"\d+"' dom_snapshot.html | head -20

echo ""
echo "===== First 300 chars of each script tag ====="
python3 -c "
import re
html = open('dom_snapshot.html', encoding='utf-8').read()
scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
for i, s in enumerate(scripts):
    print(f'--- Script {i+1} (len={len(s)}) ---')
    print(s[:500])
    print()
"

echo ""
echo "===== Checking for LinkedIn Voyager API calls in page ====="
grep -oP '"https://www\.linkedin\.com/voyager[^"]*"' dom_snapshot.html | head -20

echo ""
echo "===== All text content of anchors ====="
python3 -c "
import re
html = open('dom_snapshot.html', encoding='utf-8').read()
anchors = re.findall(r'<a[^>]*href=[^>]*>(.*?)</a>', html, re.DOTALL)
for a in anchors[:30]:
    text = re.sub(r'<[^>]*>', '', a).strip()
    if text:
        print(repr(text[:120]))
"
