"""
This package contains code to do all kinds of VO related stuff at ARI/ZAH.

gavo itself contains a couple of configuration items.  Most importantly,
you can specify where your vo tree is through the environment variable
GAVO_HOME.

Many applications want to log; by default, these logs go into $GAVO_HOME/logs,
which may be a shared directory, and that probably is not what you want.
To change this, set GAVO_LOGDIR.

gavo defines the following paths (defaults are in parentheses):

 * rootDir -- root of all vo-related data (/home/gavo)
 * inputsDir -- root of directories containing raw products (rootDir/inputs)
 * cacheDir -- directory for precomputed data (should ideally be local --
     rootDir/cache)
 * logDir -- directory to put logs in (rootDir/logs)
 * tempDir -- self-explanatory; for now is /tmp, but as another layer
     of protection should probably go to a vo-private directory
"""

import os
import sys

class Error(Exception):
	"""is the "master" exception type for gavo related stuff.

	Modules should usually derive their exceptions from this.
	"""
	pass


class InfoException(Error):
	"""should be used when something non-fatal happened that the user may
	want to know about.  When catching exceptions, these not lead to an
	abort.
	"""
	pass


class StopOperation(Error):
	"""should be used when the governing operation should be aborted for some
	reason.
	"""
	pass


rootDir = os.environ.get("GAVO_HOME", "/home/gavo")
inputsDir = os.path.join(rootDir, "inputs")
cacheDir = os.path.join(rootDir, "cache")
logDir = os.environ.get("GAVO_LOGDIR", os.path.join(rootDir, "logs"))
tempDir = os.path.join("/tmp")
