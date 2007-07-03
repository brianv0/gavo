import gavo
import re
import os

class Error(Exception):
	pass

import sys

def evaluateEnvironment(environ):
	"""sets a couple of global attributes.

	This is moved to a function since the querulator may run with
	"deferred" environments (i.e., modpython), where the "true" values
	of the environment variables are not available while importing
	querulator, or where these variables are not in os.environ.
	"""
	global templateRoot, rootURL, staticURL
	templateRoot = os.path.join(environ.get("GAVO_HOME", gavo.defaultRoot),
		"web", "querulator", "templates")
	rootURL = environ.get("QU_ROOT", "/db")
	staticURL = environ.get("QU_STATIC", "/qstatic")

evaluateEnvironment(os.environ)


def resolvePath(rootPath, relpath):
	relpath = relpath.lstrip("/")
	fullpath = os.path.realpath(os.path.join(rootPath, relpath))
	if not fullpath.startswith(rootPath):
		raise Error("I believe you are cheating -- you just tried to"
			" access %s, which I am not authorized to give you."%fullpath)
	if not os.path.exists(fullpath):
		raise Error("Invalid path %s.  This should not happen."%fullpath)
	return fullpath


def resolveTemplate(relpath):
	return resolvePath(templateRoot, relpath)


queryElementPat = re.compile(r"(?s)<\?(\w*)query (.*?)\?>")
metaElementPat = re.compile(r"(?s)<\?meta(.*?)\?>")
macroPat = re.compile(r"(?s)<\?macro(.*?)\?>")
