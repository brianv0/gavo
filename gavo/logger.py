"""
Some helpers for logging events in the data center.

The module primarily defines a member logger which is a 
"""

# XXX TODO: Remove this after making sure nobody still uses it.
import os
import sys
import logging
import logging.handlers

from gavo import base

_logLevelDict = {
	"debug": logging.DEBUG,
	"info": logging.INFO,
	"warning": logging.WARNING,
	"error": logging.ERROR,
}

logger = logging.getLogger("gavo")
_logFile = os.path.join(base.getConfig("logDir"), "gavoops")
try:
	_handler = logging.handlers.RotatingFileHandler(_logFile, "a", 1000000, 10)
except IOError:
	#sys.stderr.write("Could not open logfile %s, writing to stderr.\n"%
	#	_logFile)
	_handler = logging.StreamHandler()
_handler.setFormatter(
	logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(_handler)
logger.setLevel(_logLevelDict[base.getConfig("logLevel")])

critical = logger.critical
error = logger.error
warning = logger.warning
info = logger.info
debug = logger.debug
