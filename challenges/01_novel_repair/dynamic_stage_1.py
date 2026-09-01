import sys
import subprocess, sys, os
res = subprocess.run([sys.executable, '-m', 'pytest', '-v', 'fixture/tests/test_public.py'])
sys.exit(res.returncode)