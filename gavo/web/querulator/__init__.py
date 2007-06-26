import gavo
import re
import os

class Error(Exception):
	pass

templateRoot = os.path.join(gavo.rootDir, "web", "querulator", "templates")
rootURL = os.environ.get("QU_ROOT", "/db")
staticURL = os.environ.get("QU_STATIC", "/qstatic")
serverURL = "http://"+os.environ.get("SERVER_NAME", "")


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
