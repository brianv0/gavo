import gavo
from gavo.web import common
import re
import os

class Error(Exception):
	pass

import sys

def evaluateEnvironment(environ):
	"""sets a couple of global attributes.

	Don't use these attribute any more, get a context and take their
	counterparts from there.

	This is moved to a function since the querulator may run with
	"deferred" environments (i.e., modpython), where the "true" values
	of the environment variables are not available while importing
	querulator, or where these variables are not in os.environ.
	"""
	global templateRoot, rootURL, staticURL
	templateRoot = os.path.join(gavo.rootDir,
		"web", "querulator", "templates")
	rootURL = environ.get("QU_ROOT", "/db")
	staticURL = environ.get("QU_STATIC", "/qstatic")

evaluateEnvironment(os.environ)


def resolveTemplate(relpath):
	return common.resolvePath(templateRoot, relpath)


queryElementPat = re.compile(r"(?s)<\?(\w*)query (.*?)\?>")
metaElementPat = re.compile(r"(?s)<\?meta(.*?)\?>")
macroPat = re.compile(r"(?s)<\?macro(.*?)\?>")
