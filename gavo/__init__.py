"""
This package contains code to do all kinds of VO related stuff at ARI/ZAH.
"""

import os
import sys


class Error(Exception):
	"""is the "master" exception type for gavo related stuff.

	Modules should usually derive their exceptions from this.
	"""
	pass


class InfoException(Error):
	"""should be used when something non-fatal happened that the user may
	want to know about.  When catching exceptions, these not lead to an
	abort.
	"""
	pass


class StopOperation(Error):
	"""should be used when the governing operation should be aborted for some
	reason.
	"""
	pass
