"""Allowlisted sync diagnostics; never persist upstream responses or exception text."""
CODES={'comparison_invalid','read_failed','write_rejected','write_unknown','readback_failed','readback_mismatch','ownership_conflict'}
TABLES={'Comparisons','PlatformCandidates','Discogs','Sources','Inputs','Analysis'}
class SyncFailure(ValueError):
    def __init__(self, code, tables=()):
        self.code=code if code in CODES else 'read_failed'
        self.tables=sorted({t for t in tables if t in TABLES})
        super().__init__('Google Sheet sync check failed')
    def report(self):
        return {'step':'sheets','error':'SyncFailure','code':self.code,'tables':self.tables}

def report(exc):
    return exc.report() if type(exc) is SyncFailure else {'step':'sheets','error':type(exc).__name__}
