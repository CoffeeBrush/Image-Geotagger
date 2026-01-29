#!/usr/bin/env python3
"""Extract version from version_info.txt for Inno Setup"""

import re

with open('version_info.txt', 'r') as f:
    content = f.read()

# Search for ProductVersion line
match = re.search(r"StringStruct\('ProductVersion', '([^']+)'\)", content)
if match:
    version = match.group(1)
    print(f"#define AppVersion \"{version}\"")
else:
    print("#define AppVersion \"1.0.0\"")
