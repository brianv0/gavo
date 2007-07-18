"""
Common functions and classes for gavo web interfaces.

(Much of what would belong here currently lives within querulator.
We'll move the stuff as we see fit...)
"""

import os

import gavo

class Error(gavo.Error):
	pass


def resolvePath(rootPath, relPath):
	"""joins relPath to rootPath and makes sure the result really is
	in rootPath.
	"""
	relPath = relPath.lstrip("/")
	fullPath = os.path.realpath(os.path.join(rootPath, relPath))
	if not fullPath.startswith(rootPath):
		raise Error("I believe you are cheating -- you just tried to"
			" access %s, which I am not authorized to give you."%fullPath)
	if not os.path.exists(fullPath):
		raise Error("Invalid path %s.  This should not happen."%fullPath)
	return fullPath


def getSubmitButtons():
	"""returns HTML for submit buttons for the various formats we can do.
	"""
	return ('<p class="submitbuttons">'
		'<input type="submit" value="Table as HTML" name="submit">\n'
		'\n<input type="submit" value="Table as VOTable"'
		' name="submit-votable">\n'
		'</p>')
