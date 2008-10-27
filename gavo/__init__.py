"""
This package contains code to do all kinds of VO related stuff at ARI/ZAH.
"""

import os
import sys


try:
	import cElementTree as ElementTree
except ImportError:
	from elementtree import ElementTree


try:
	from twisted.python.failure import Failure
except ImportError:
	class Failure(Exception):
		pass


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
		self.msg = msg
		self.fieldName, self.record = fieldName, record
	
	def __str__(self):
		recStr = ""
		if self.record:
			recStr = ", found in: record %s"%repr(self.record)
		return "%s%s"%(self.msg, recStr)


class PermissionDenied(Error):
	"""is raised on unauthorized access to a protected resource.
	"""

class RdNotFound(Error):
	"""is raised when importParser.getRd cannot locate a resource descriptor.
	"""
# It is defined here since importing importparser is a no-no for most
# modules.
	pass


class MetaError(Error): 
	pass


class MetaSyntaxError(MetaError):
	pass

class NoMetaKey(MetaError):
	pass

class MetaCardError(MetaError):
	pass


def raiseTb(exCls, msg, *args):
	"""raises an exception exCls(*args) furnished with the current traceback

	This is supposed to be used when re-raising exceptions.  It's bad that
	this function shows up in the traceback, but without macros, there's
	little I can do about it.

	msg may be a twisted Failure instance.  In that case, the traceback
	and the message are taken from it.
	"""
	if isinstance(msg, Failure):
		raise exCls, (msg.getErrorMessage(),)+args, msg.tb
	else:
		raise exCls, (msg,)+args, sys.exc_info()[-1]


floatRE = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
