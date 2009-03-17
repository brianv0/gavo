"""
OS abstractions and related.
"""

import os


def safeclose(f):
	"""syncs and closes the python file f.

	You generally want to use this rather than a plain close() before
	overwriting a file with a new version.
	"""
	f.flush()
	os.fsync(f.fileno())
	f.close()
