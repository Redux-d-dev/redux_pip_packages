import glob
from setuptools import setup

def collect_requirements():
    """Find every requirements.txt anywhere under src/, merge, dedupe.
    Runs at install/build time only — never writes to disk."""
    reqs = set()
    for path in glob.glob("src/**/requirements.txt", recursive=True):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    reqs.add(line)
    return sorted(reqs)

setup(
    install_requires=collect_requirements(),
)