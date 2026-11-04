import re
from pathlib import Path

pat = re.compile(r'(docs/[^\s`)|、，。]+?/)(docs/\1)')
fixed = []
for md in Path('.').rglob('*.md'):
    if '.git' in str(md) or 'archive' in str(md) or 'projects' in str(md):
        continue
    text = md.read_text(encoding='utf-8')
    new = text
    for _ in range(3):
        new = re.sub(r'docs/([^\s`)|、，。]+?)/docs/\1/', r'docs/\1/', new)
    if new != text:
        md.write_text(new, encoding='utf-8', newline='\n')
        fixed.append(str(md))
print('fixed files:', len(fixed))
for f in fixed:
    print(' ', f)
