"""Run tests that need no listening socket; explicitly report excluded suites."""
import sys,unittest
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
suite=unittest.defaultTestLoader.discover(str(root/'tests'))
def cases(s):
 for test in s:
  if isinstance(test,unittest.TestSuite):yield from cases(test)
  else:yield test
all_tests=list(cases(suite))
excluded={'test_dashboard','test_full_workflow'}
selected=[t for t in all_tests if t.__class__.__module__ not in excluded]
print(f'Offline verification: {len(selected)} tests; {len(all_tests)-len(selected)} socket tests NOT RUN.',flush=True)
result=unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(selected))
raise SystemExit(not result.wasSuccessful())
