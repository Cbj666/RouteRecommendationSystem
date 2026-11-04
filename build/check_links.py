import re, pathlib
root = pathlib.Path('.')
bad = []
for f in ['docs/项目说明书.md', 'docs/分工卡片.md', 'docs/项目交接说明.md']:
    txt = pathlib.Path(f).read_text(encoding='utf-8')
    for m in re.findall(r'`([^`\n]*?\.(?:md|py|png|pptx|csv|gpkg|json))`', txt):
        p = (root / m)
        if '*' in m or m.startswith('http'):
            continue
        if not p.exists():
            bad.append((f, m))
seen = set()
for f, m in bad:
    if (f, m) in seen: continue
    seen.add((f, m))
    print(f'  missing: {f} -> {m}')
print('missing total:', len(seen))
