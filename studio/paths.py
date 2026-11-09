"""Central paths; never resolve a sibling upstream checkout."""
import os
import sys
from pathlib import Path
APP_ROOT=Path(__file__).resolve().parent.parent
VENDOR_ROOT=APP_ROOT/'vendor/moneyprinterturbo'
DATA_ROOT=Path(os.environ.get('STUDIO_DATA',APP_ROOT/'data')).resolve()
ENGINE_RUNTIME=DATA_ROOT/'quick-engine'
PYTHON=Path(os.environ.get('STUDIO_PYTHON', APP_ROOT/'.venv/bin/python'))
