"""
This module defines an abstract superclass for all grammars.
"""

from gavo import logger
from gavo import nullui
from gavo import parsing
from gavo import record
from gavo import sqlsupport
from gavo import utils
from gavo.parsing import conditions
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
	_grammarAttributes = set(["docIsRow"])

	def __init__(self, additionalFields={}, initvals={}):
		fields = {
			"macros": record.ListField,      # macros to be applied
			"rowProcs": record.ListField,    # row processors to be applied
			"constraints": None,             # constraints on rowdicts
			"docIsRow": record.BooleanField, # apply row macros to docdict 
                                       # and ship it as a row?
		}
		fields.update(additionalFields)
		record.Record.__init__(self, fields, initvals=initvals)
		self.curInputFileName = None
	
	def parse(self, parseContext):
		getattr(self, "_setupParse", lambda _: None)(parseContext)
		counter = gavo.ui.getGoodBadCounter("Importing rows", 100, 
			parseContext.silent)
		row = "<unparsed docrow>"
		try:
			try:
				row = self._getDocdict(parseContext)
				self.handleDocdict(row, parseContext)
			except gavo.Error:
				raise
			except Exception, msg:
				utils.raiseTb(gavo.ValidationError, 
					"Failure while parsing doc %s (%s)"%(row, msg),
					utils.getErrorField())
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
				except gavo.StopOperation:
					counter.hit()
					raise
				except KeyboardInterrupt:
					raise
				except gavo.ValidationError:
					raise
				except gavo.InfoException, msg:
					logger.info(msg)
				except gavo.parsing.ParseError, msg:
					errmsg = "Parse failure, aborting source (%s)."%msg
					counter.hitBad()
					raise utils.raiseTb(gavo.ValidationError, errmsg,
						utils.getErrorField())
				except sqlsupport.OperationalError, msg:
					gavo.ui.displayError("Import of row %s failed (%s). ABORTING"
						" OPERATION."%(row, msg))
					counter.hitBad()
					raise
				except Exception, msg:
					counter.hitBad()
					utils.raiseTb(gavo.ValidationError, 
						"Failure while parsing rec %s (%s)"%(row, msg), 
						utils.getErrorField())
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
		try:
			if self.get_constraints():
				self.get_constraints().check(rowdict)
		except conditions.SkipRecord, err:
			if parsing.verbose:
				logger.info("Skipping rowdict %s because constraint %s failed to"
					" satisfied"%(record, err.constraint))
		for processedDict in self._process(rowdict, parseContext):
			parseContext.processRowdict(processedDict)

	def enableDebug(self, aList):
		pass
