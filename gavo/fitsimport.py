"""
This is another (very rudimentary) fits ingestor
"""

import os

from gavo import fitstools


class Error(Exception):
	pass


class FitsMapper:
	"""is a model for the mapping between FITS header fields and database
	entries.

	Basically, we define a table and the fits headers that should go into
	the database.  This is done through a text file giving, one line at
	a time
	<db column name> <db type> <fits header field> {<optkey>=<optval>}

	If the fits header field is ., the db column name will be filled in.

	If the fits header field is @, a macro of the same name will be
	called to get the desired values.  The macro receives the path
	to the file and the header itself.  Macros are defined by clients and
	passed in through the macros argument.
	"""
	def __init__(self, srcFile, macros={}):
		self.macros = macros
		self._parseSource(srcFile)

	def _parseDefLine(self, ln):
		defs = ln.split()
		if defs[2]==".":
			defs[2] = defs[0]
		if defs[2].startswith("@"):
			defs[2] = self.macros[defs[2][1:]]
		return (defs[0].lower(), defs[1], defs[2],
			dict([(key, val) 
				for key, val in [d.split("=") for d in defs[3:]]]))

	def _parseSource(self, srcFile):
		"""parses the specification file.
		"""
		self.fieldDescs = []
		for ln in open(srcFile):
			if not ln.strip() or ln.startswith("#"):
				continue
			try:
				self.fieldDescs.append(self._parseDefLine(ln))
			except Exception, msg:
				raise Error("Error in line %s (%s)"%(repr(ln), msg))
	
	def getTableDef(self):
		"""returns a table definition suitable for sqlsupport.TableWriter
		"""
		return [(d[0], d[1], d[3]) for d in self.fieldDescs]

	def _parseHeader(self, header, fName):
		valDict = {}
		for dbName, _, srcDesc, _ in self.fieldDescs:
			if isinstance(srcDesc, basestring):
				valDict[dbName] = header[srcDesc]
			else:
				valDict[dbName] = srcDesc(header, fName)
		return valDict

	def feedFiles(self, fNames, feedFunc):
		"""feeds the headers from all fits files named in the sequence
		fNames into the database.
		"""
		for fName in fNames:
			hdus = fitstools.openFits(fName)
			feedFunc(self._parseHeader(hdus[0].header, fName))
