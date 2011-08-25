"""
OS abstractions and related.
"""

#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.

import os
import urllib2

from gavo.utils import misctricks


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


def fgetmtime(fileobj):
	"""returns the mtime of the file below fileobj.

	This raises an os.error if that file cannot be fstated.
	"""
	try:
		return os.fstat(fileobj.fileno()).st_mtime
	except AttributeError:
		raise misctricks.logOldExc(os.error("Not a file: %s"%repr(fileobj)))


def cat(srcF, destF, chunkSize=1<<20):
	"""reads srcF into destF in chunks.
	"""
	while True:
		data = srcF.read(chunkSize)
		if not data:
			break
		destF.write(data)

def ensureDir(dirPath, mode=None, setGroupTo=None):
	"""makes sure that dirPath exists and is a directory.

	If dirPath does not exist, it is created, and its permissions are
	set to mode with group ownership setGroupTo if those are given.

	setGroupTo must be a numerical gid if given.

	This function may raise all kinds of os.errors if something goes
	wrong.  These probably should be handed through all the way to the
	user since when something fails here, there's usually little
	the program can safely do to recover.
	"""
	if os.path.exists(dirPath):
		return
	os.mkdir(dirPath)
	if mode is not None:
		os.chmod(dirPath, mode)
	if setGroupTo:
		os.chown(dirPath, -1, setGroupTo)
