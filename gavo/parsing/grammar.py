"""
This module defines an abstract superclass for all grammars.
"""

from gavo import record
from gavo import logger
from gavo import parsing
from gavo import sqlsupport
import gavo


class ParseError(gavo.Error):
	pass


class Grammar(record.Record):
	"""is an abstract grammar.

	Grammars communicate with the rest of the world through their parse
	method that receives a ParseContext instance.

	Grammars not overriding parse need to define:

		* _getDocdict() -- returns a dict of toplevel productions
		* _iterRows(parseContext) -- iterates over all rows in the document, should
		  raise a ParseError for malformed rows.
	
	They may provide methods
	 * _setupParse(parseContext)
	 * _cleanupParse(parseContext)
	
	The built-in _parse first calls _setupParse, then _getDocdict, then
	_iterRows. 

	Hand-rolled parse methods must call handleRowdict and handleDocdict.

	Grammar classes should also provide an enableDebug method that
	accepts a list of symbol names that they should print some sort
	of debug info for.
	"""
	def __init__(self, fieldDefs):
		fieldDefs.update({
			"macros": record.ListField,      # macros to be applied
			"rowProcs": record.ListField,    # row processors to be applied
			"docIsRow": record.BooleanField, # apply row macros to docdict 
                                       # and ship it as a row?
		})
		record.Record.__init__(self, fieldDefs)
		self.curInputFileName = None
	
	def _handleInternalError(self, exc, row):
		if parsing.verbose:
			import traceback
			traceback.print_exc()
		msg = ("Internal Error (%s, %s) while parsing row %s -- run with -v to"
			" see traceback."%(exc.__class__.__name__, str(exc), str(row)[:120]))
		gavo.ui.displayError(msg)
		raise gavo.Error(msg)

	def parse(self, parseContext):
		getattr(self, "_setupParse", lambda _: None)(parseContext)
		counter = gavo.ui.getGoodBadCounter("Importing rows", 100)
		try:
			try:
				row = self._getDocdict(parseContext)
				self.handleDocdict(row, parseContext)
			except gavo.Error:
				raise
			except Exception, msg:
				self._handleInternalError(msg, row)
			lines = self._iterRows(parseContext)
			# We use this funny loop to handle exceptions raised while the
			# grammar matches a row in the exception handlers below (it would
			# be hard to get an appropriate row count otherwise)
			while 1:
				try:
					row = lines.next()
					self.handleRowdict(row, parseContext)
					counter.hit()
				except StopIteration:
					break
				except (gavo.StopOperation, KeyboardInterrupt):
					raise
				except gavo.InfoException, msg:
					logger.info(msg)
				except gavo.parsing.ParseError, msg:
					errmsg = "Parse failure, aborting source (%s). See log."%msg
					counter.hitBad()
					logger.error(errmsg, exc_info=True)
					raise gavo.Error(errmsg)
				except sqlsupport.OperationalError, msg:
					logger.error("Row %s bad (%s).  Ignoring."%(row, msg))
					gavo.ui.displayError("Import of row %s failed (%s). ABORTING"
						" OPERATION."%(row, msg))
					counter.hitBad()
					raise  # XXXXXXXXX should emit err msg wherever this is caught.
				except Exception, msg:
					counter.hitBad()
					self._handleInternalError(msg, row)
		finally:
			getattr(self, "_cleanupParse", lambda _: None)(parseContext)
			counter.close()

	def _runProcessors(self, rowdict, parseContext):
		"""processes rowdict with all row processors and returns all
		resulting rows.
		"""
		currentRows = [rowdict]
		for proc in self.get_rowProcs():
			newRows = []
			for row in currentRows:
				newRows.extend(proc(parseContext.atExpand, rowdict))
			currentRows = newRows
		return currentRows

	def _expandMacros(self, rowdict, parseContext):
		for macro in self.get_macros():
			macro(parseContext.atExpand, rowdict)

	def _process(self, rowdict, parseContext):
		"""runs row processors and macros on rowdict.
		"""
		for row in self._runProcessors(rowdict, parseContext):
			self._expandMacros(row, parseContext)
			yield row

	def handleDocdict(self, docdict, parseContext):
		"""should be called by derived classes whenever a new document
		has been parsed.

		The argument is a dict mapping preterminal names to their values.
		"""
		if self.get_docIsRow():
			self.handleRowdict(docdict, parseContext)
		else:
			parseContext.processDocdict(docdict)

	def handleRowdict(self, rowdict, parseContext):
		"""should be called by derived classes whenever a new row
		has been parsed.

		The argument is a dict mapping preterminal names to their values.
		"""
		for processedDict in self._process(rowdict, parseContext):
			parseContext.processRowdict(processedDict)

	def enableDebug(self, aList):
		pass
