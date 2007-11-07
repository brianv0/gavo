"""
This package contains code to do all kinds of VO related stuff at ARI/ZAH.
"""

import os
import sys


class Error(Exception):
	"""is the "master" exception type for gavo related stuff.

	Modules should usually derive their exceptions from this.
	"""

class FatalError(Error):
	"""should be called whenever the current operation can't be sensibly
	completed and must be aborted.
	"""


class InfoException(Error):
	"""should be used when something non-fatal happened that the user may
	want to know about.  When catching exceptions, these not lead to an
	abort.
	"""


class StopOperation(Error):
	"""should be used when the governing operation should be aborted due
	to some sort of user request.
	"""


class ValidationError(Error):
	"""is raised when the validation of a field fails.  It has a field
	attribute containing the field name and an optional record attribute
	saying which record caused the error.
	"""
	def __init__(self, msg, fieldName, record=None):
		Error.__init__(self, msg)
		self.fieldName, self.record = fieldName, record

