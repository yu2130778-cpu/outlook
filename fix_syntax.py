#!/usr/bin/env python3
"""Fix f-string syntax errors in unlock_and_fetch_rt.py"""
import re

path = '/home/workspace/Email-Register/unlock_and_fetch_rt.py'
with open(path, 'r') as f:
    lines = f.readlines()

fixed = 0
for i, line in enumerate(lines):
    # Fix { b.click(); } -> {{ b.click(); break; }}
    if '{ b.click(); }' in line and 'for (const b of btns)' not in line:
        lines[i] = line.replace('{ b.click(); }', '{{ b.click(); break; }}')
        fixed += 1
        print(f"Fixed line {i+1}: {line.strip()}")
    
    # Fix { btn.click(); } -> {{ btn.click(); }}
    if '{ btn.click(); }' in line:
        lines[i] = line.replace('{ btn.click(); }', '{{ btn.click(); }}')
        fixed += 1
        print(f"Fixed line {i+1}: {line.strip()}")
    
    # Fix { b.click(); return t; } -> {{ b.click(); return t; }}
    if '{ b.click(); return' in line and '{{' not in line:
        lines[i] = line.replace('{ b.click(); return', '{{ b.click(); return').rstrip()
        if not lines[i].endswith('}}'):
            lines[i] = lines[i].rstrip('\n').replace('}', '}}') + '\n'
        fixed += 1
        print(f"Fixed line {i+1}: {line.strip()}")

with open(path, 'w') as f:
    f.writelines(lines)

print(f"\nTotal fixes: {fixed}")
