"""
Basic OS interface/utility functions that depend on our configuration.

(everything that doesn't need getConfig is somewhere in gavo.utils)
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import grp
import re
import os
import subprocess
import time
from email import charset
from email import utils as emailutils
from email.header import Header
from email.parser import Parser
from email.mime.nonmultipart import MIMENonMultipart


import pkg_resources

from gavo.base import config
from gavo import utils


def getGroupId():
	gavoGroup = config.get("group")
	try:
		return grp.getgrnam(gavoGroup)[2]
	except KeyError, ex:
		raise utils.ReportableError("Group %s does not exist"%str(ex),
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
			raise utils.ReportableError(
				"Could not create directory %s"%path,
				hint="The operating system reported: %s"%err)
		except Exception, msg:
			raise utils.ReportableError(
				"Could not create directory %s (%s)"%(path, msg))

	gavoGroup = getGroupId()
	stats = os.stat(path)
	if stats.st_mode&0060!=060 or stats.st_gid!=gavoGroup:
		try:
			os.chown(path, -1, gavoGroup)
			if writable:
				os.chmod(path, stats.st_mode | 0060)
		except Exception, msg:
			raise utils.ReportableError(
				"Cannot set %s to group ownership %s, group writable"%(
					path, gavoGroup),
				hint="Certain directories must be writable by multiple user ids."
				"  They must therefore belong to the group %s and be group"
				" writeable.  The attempt to make sure that's so just failed"
				" with the error message %s."
				"  Either grant the directory in question to yourself, or"
				" fix permissions manually.  If you own the directory and"
				" sill see permission errors, try 'newgrp %s'"%(
					config.get("group"), msg, config.get("group")))


@utils.document
def makeSitePath(path):
	"""returns a rooted local part for a server-internal URL.

	uri itself needs to be server-absolute; a leading slash is recommended
	for clarity but not mandatory.
	"""
	return str(config.get("web", "nevowRoot")+path.lstrip("/"))


@utils.document
def makeAbsoluteURL(path):
	"""returns a fully qualified URL for a rooted local part.
	"""
	return str(config.get("web", "serverURL")+makeSitePath(path))


def getBinaryName(baseName):
	"""returns the name of a binary it thinks is appropriate for the platform.

	To do this, it asks config for the platform name, sees if there's a binary
	<bin>-<platname> if platform is nonempty.  If it exists, it returns that name,
	in all other cases, it returns baseName unchanged.
	"""
	platform = config.get("platform")
	if platform:
		platName = baseName+"-"+platform
		if os.path.exists(platName):
			return platName
	return baseName


def openDistFile(name):
	"""returns an open file for a "dist resource", i.e., a file distributed
	with DaCHS.

	This is like pkg_resources, except it also checks in 
	$GAVO_DIR/override/<name> and returns that file if present.  Thus, you
	can usually override DaCHS built-in files (but there's not too many
	places in which that's used so far).

	TODO: this overrides stuff stinks a bit because for many classes 
	of files (RDs, templates, ...) there already are override locations.
	It think we should compute the override path based on name prefixes.
	"""
	userPath = os.path.join(config.get("rootDir"), "overrides/"+name)
	if os.path.exists(userPath):
		return open(userPath)
	else:
		return pkg_resources.resource_stream('gavo', "resources/"+name)


def getVersion():
	"""returns (as a string) the DaCHS version running.

	The information is obtained from setuptools.
	"""
	return pkg_resources.require("gavodachs")[0].version


def formatMail(mailText):
	"""returns a mail with headers and content properly formatted as
	a bytestring and MIME.

	mailText must be a unicode instance or pure ASCII
	"""
	rawHeaders, rawBody = mailText.split("\n\n", 1)
	cs = charset.Charset("utf-8")
	cs.body_encoding = charset.QP
	cs.header_encoding = charset.QP
	# they've botched MIMEText so bad it can't really generate 
	# quoted-printable UTF-8 any more.  So, let's forget MIMEText:
	msg = MIMENonMultipart("text", "plain", charset="utf-8")
	msg.set_payload(rawBody, charset=cs)

	for key, value in Parser().parsestr(rawHeaders.encode("utf-8")).items():
		if re.match("[ -~]*$", value):
			# it's plain ASCII, don't needlessly uglify output
			msg[key] = value
		else:
			msg[key] = Header(value, cs)
	msg["Date"] = emailutils.formatdate(time.time(), 
		localtime=False, usegmt=True)
	msg["X-Mailer"] = "DaCHS VO Server"
	return msg.as_string()


def sendMail(mailText):
	"""sends mailText (which has to have all the headers) via sendmail.

	(which is configured in [general]sendmail).

	This will return True when sendmail has accepted the mail, False 
	otherwise.
	"""
	mailText = formatMail(mailText)

	pipe = subprocess.Popen(config.get("sendmail"), shell=True,
		stdin=subprocess.PIPE)
	pipe.stdin.write(mailText)
	pipe.stdin.close()

	if pipe.wait():
		utils.sendUIEvent("Error", "Wanted to send mail starting with"
			" '%s', but sendmail returned an error message"
			" (check the [general]sendmail setting)."%
				utils.makeEllipsis(mailText, 300))
		return False
	
	return True
