"""
Run this script once to create all __init__.py files.
From your project root: python create_init_files.py
"""
from pathlib import Path

packages = [
    "backend/__init__.py",
    "backend/api/__init__.py",
    "backend/rag/__init__.py",
    "backend/nlq/__init__.py",
    "backend/guardrails/__init__.py",
    "backend/observability/__init__.py",
    "backend/auth/__init__.py",
]

for path_str in packages:
    p = Path(path_str)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("")
    print(f"✅ Created: {path_str}")

print("\nDone! All __init__.py files created.")
