"""
OS abstractions and related.
"""

#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.

import os
import urllib2


def safeclose(f):
	"""syncs and closes the python file f.

	You generally want to use this rather than a plain close() before
	overwriting a file with a new version.
	"""
	f.flush()
	os.fsync(f.fileno())
	f.close()


_restrictedURLOpener = urllib2.OpenerDirector()
_restrictedURLOpener.add_handler(urllib2.HTTPRedirectHandler())
_restrictedURLOpener.add_handler(urllib2.HTTPHandler())
_restrictedURLOpener.add_handler(urllib2.HTTPSHandler())
_restrictedURLOpener.add_handler(urllib2.FTPHandler())
_restrictedURLOpener.add_handler(urllib2.UnknownHandler())

def urlopenRemote(url, data=None):
	"""works like urllib2.urlopen, except only http, https, and ftp URLs
	are handled.

	The function also massages the error messages of urllib2 a bit.  urllib2
	errors always become IOErrors (which is more convenient within the DC).
	"""
	try:
		return _restrictedURLOpener.open(url, data)
	except (urllib2.URLError, ValueError), msg:
		msgStr = msg.args[0]
		if isinstance(msgStr, Exception):
			try:  # maybe it's an os/socket type error
				msgStr = msgStr.args[1]
			except IndexError:  # maybe not...
				pass
		if not isinstance(msgStr, basestring):
			msgStr = str(msg)
		raise IOError("Could not open URL %s: %s"%(url, msgStr))
