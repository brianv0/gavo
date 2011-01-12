"""
Initial setup for the file system hierarchy.

This module is supposed to create as much of the DaCHS file system environment
as possible.  Take care to give sensible error messages -- much can go wrong
here, and it's nice if the user has a way to figure out what's wrong.
"""

from __future__ import with_statement

import grp
import os
import sys
import textwrap

from gavo import base


def bailOut(msg, hint=None):
	sys.stderr.write("*** Error: %s\n\n"%msg)
	if hint is not None:
		sys.stderr.write(textwrap.fill(hint)+"\n")
	sys.exit(1)


def unindentString(s):
	return "\n".join(s.strip() for s in s.split("\n"))+"\n"


def makeRoot():
	rootDir = base.getConfig("rootDir")
	if os.path.isdir(rootDir):
		return
	try:
		os.makedirs(rootDir)
	except os.error:
		bailOut("Cannot create root directory %s."%rootDir,
			"This usually means that the current user has insufficient privileges"
			" to write to the parent directory.  To fix this, either have rootDir"
			" somewhere you can write to (edit /etc/gavorc) or create the directory"
			" as root and grant it to your user id.")


def getGroupId():
	gavoGroup = base.getConfig("group")
	try:
		return grp.getgrnam(gavoGroup)[2]
	except KeyError, ex:
		bailOut("Group %s does not exist"%str(ex),
			"You should have created this (unix) group when you created the server"
			" user (usually, 'gavo').  Just do it now and re-run this program.")


def makeDirVerbose(path):
	if not os.path.isdir(path):
		try:
			os.makedirs(path)
		except os.error, err:
			bailOut("Could not create directory %s (%s)"%(
				path, err))  # add hints
		except Exception, msg:
			bailOut("Could not create directory %s (%s)"%(
				path, msg))


_GAVO_WRITABLE_DIRS = set([
	"cacheDir",
	"logDir",
	"tempDir",])

def makeDirForConfig(configKey, gavoGrpId):
	path = base.getConfig(configKey)
	makeDirVerbose(path)
	if configKey in _GAVO_WRITABLE_DIRS:
		stats = os.stat(path)
		if stats.st_mode&0060!=060 or stats.st_gid!=gavoGrpId:
			try:
				os.chown(path, -1, gavoGrpId)
				os.chmod(path, stats.st_mode | 0060)
			except Exception, msg:
				bailOut("Cannot set %s to group ownership %s, group writable"%(
					path, gavoGrpId),
					hint="Certain directories must be writable by multiple user ids."
					"  They must therefore belong to the group %s and be group"
					" writeable.  The attempt to make sure that's so just failed"
					" with the error message %s."
					"  Either grant the directory in question to yourself, or"
					" fix permissions manually.  If you own the directory and"
					" sill see permission errors, try 'newgrp %s'"%(
						base.getConfig("group"), msg, base.getConfig("group")))


def makeDefaultMeta():
	destPath = os.path.join(base.getConfig("configDir"), "defaultmeta.txt")
	if os.path.exists(destPath):
		return
	rawData = """publisher: Fill Out
		publisher.ivoId: ivo://not_filled_out
		contact.name: Fill Out
		contact.address: Ordinary street address.
		contact.email: Your email address
		contact.telephone: Alternatively, delete this line
		creator.name: Could be same as contact.name
		creator.logo: a URL pointing to a small png
		_noresultwarning: Your query did not match any data."""
	with open(destPath, "w") as f:
		f.write(unindentString(rawData))


def makeProfiles():
	profilePath = base.getConfig("configDir")
	for fName, content in [
			("dsn", "#host = computer.doma.in\n#port = 5432\ndatabase = gavo\n"),
			("feed", "include dsn\nuser = gavoadmin\npassword = \n"),
			("trustedquery", "include dsn\nuser = gavo\npassword = \n"),
			("untrustedquery", "include dsn\nuser = untrusted\npassword = \n"),]:
		destPath = os.path.join(profilePath, fName)
		if not os.path.exists(destPath):
			with open(destPath, "w") as f:
				f.write(content)

def prepareWeb():
	makeDirVerbose(os.path.join(base.getConfig("webDir"), "nv_static"))


def main():
	makeRoot()
	grpId = getGroupId()
	for configKey in ["configDir", "inputsDir", "cacheDir", "logDir", 
			"tempDir", "webDir", "stateDir"]:
		makeDirForConfig(configKey, grpId)
	makeDefaultMeta()
	makeProfiles()
	prepareWeb()
