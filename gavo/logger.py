"""
Some helpers for logging VO events.

The module primarily defines a member logger which is a 
"""

import os
import sys
import logging

import gavo
from gavo import config

logger = logging.getLogger("gavo")
_logFile = os.path.join(config.get("logDir"), "gavoops")
try:
	_handler = logging.FileHandler(_logFile)
except IOError:
	#sys.stderr.write("Could not open logfile %s, writing to stderr.\n"%
	#	_logFile)
	_handler = logging.StreamHandler()
_handler.setFormatter(
	logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)

critical = logger.critical
error = logger.error
warning = logger.warning
info = logger.info
debug = logger.debug
