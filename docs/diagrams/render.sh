#!/bin/bash
# Re-render every diagram: Mermaid sources in src/ -> PNG (2x, for the README) and SVG (scalable).
# Needs the Mermaid CLI (npm i -g @mermaid-js/mermaid-cli). Custom diagrams: python3 custom/build.py
set -euo pipefail
cd "$(dirname "$0")"
for f in src/*.mmd; do
  n=$(basename "$f" .mmd)
  mmdc -q -i "$f" -o "$n.png" -c mermaid.config.json -b '#0B1324' -s 2
  mmdc -q -i "$f" -o "$n.svg" -c mermaid.config.json -b '#0B1324'
  echo "rendered $n"
done
