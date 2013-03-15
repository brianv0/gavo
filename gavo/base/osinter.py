"""
Basic OS interface functions that depend on our configuration.

(everything that doesn't need getConfig is somewhere in gavo.utils)
"""

import grp
import os

from gavo.base import config
from gavo.utils import excs


def getGroupId():
	gavoGroup = config.get("group")
	try:
		return grp.getgrnam(gavoGroup)[2]
	except KeyError, ex:
		raise excs.ReportableError("Group %s does not exist"%str(ex),
			hint="You should have created this (unix) group when you"
			" created the server user (usually, 'gavo').  Just do it"
			" now and re-run this program.")


def makeSharedDir(path, writable=True):
	"""creates a directory with group ownership [general]group.

	There's much that can to wrong; we try to raise useful error messages.
	"""
	if not os.path.isdir(path):
		try:
			os.makedirs(path)
		except os.error, err:
			raise excs.ReportableError(
				"Could not create directory %s"%path,
				hint="The operating system reported: %s"%err)
		except Exception, msg:
			bailOut("Could not create directory %s (%s)"%(
				path, msg))

	gavoGroup = getGroupId()
	stats = os.stat(path)
	if stats.st_mode&0060!=060 or stats.st_gid!=gavoGroup:
		try:
			os.chown(path, -1, gavoGroup)
			if writable:
				os.chmod(path, stats.st_mode | 0060)
		except Exception, msg:
			raise excs.ReportableError(
				"Cannot set %s to group ownership %s, group writable"%(
					path, setGroupTo),
				hint="Certain directories must be writable by multiple user ids."
				"  They must therefore belong to the group %s and be group"
				" writeable.  The attempt to make sure that's so just failed"
				" with the error message %s."
				"  Either grant the directory in question to yourself, or"
				" fix permissions manually.  If you own the directory and"
				" sill see permission errors, try 'newgrp %s'"%(
					config.get("group"), msg, config.get("group")))

