"""
An observer doing logging of warnings, infos, errors, etc.

No synchronization takes place; it's probably not worth sweating this.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from gavo import base
from gavo.base import ObserverBase, listensTo


class LoggingUI(ObserverBase):
	def __init__(self, eh):
		ObserverBase.__init__(self, eh)
		errH = RotatingFileHandler(
			os.path.join(base.getConfig("logDir"), "dcErrors"),
			maxBytes=500000, backupCount=3)
		errH.setFormatter(
			logging.Formatter("[%(process)s] %(message)s"))
		self.errorLogger = logging.getLogger("dcErrors")
		self.errorLogger.addHandler(errH)

		infoH = RotatingFileHandler(
			os.path.join(base.getConfig("logDir"), "dcInfos"),
			maxBytes=500000, backupCount=1)
		infoH.setFormatter(
			logging.Formatter("%(levelname)s [%(process)s] %(message)s"))
		self.infoLogger = logging.getLogger("dcInfos")
		self.infoLogger.addHandler(infoH)
		self.infoLogger.setLevel(logging.DEBUG)

	@listensTo("ExceptionMutation")
	def logOldException(self, res):
		excInfo, newExc = res
		self.infoLogger.info("Swallowed the exception below, re-raising %s"%
			str(newExc), exc_info=excInfo)
	
	@listensTo("Info")
	def logInfo(self, message):
		self.infoLogger.info(message)
	
	@listensTo("Warning")
	def logWarning(self, message):
		self.infoLogger.warning(message)
	
	@listensTo("Error")
	def logError(self, message):
		self.errorLogger.error(str(message), exc_info=True)
