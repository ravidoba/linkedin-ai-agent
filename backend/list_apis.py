import json
r = json.load(open('dom_report.json'))
print(f"Total API URLs: {len(r['all_api_urls'])}")
for u in r['all_api_urls']:
    print(u)
