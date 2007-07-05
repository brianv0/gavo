"""
A grammar that just splits the source into input lines and then
exposes the fields as character ranges.

XXX TODO: The whole booster stuff is a mess right now.  We mess up
any transaction processing, and fiddling in the connection info to
the booster isn't cool either.
"""

import gavo
import grammar


class BoosterException(gavo.Error):
	pass

class BoosterNotDefined(BoosterException):
	pass

class BoosterNotAvailable(BoosterException):
	pass

class BoosterFailed(BoosterException):
	pass


class ColumnExtractor:
	"""
	>>> c = ColumnExtractor("1234567890123456789 ")
	>>> c["1"]
	'1'
	>>> c["2-4"]
	'234'
	>>> c["18-30"]
	'89'
	>>> print c["20"]
	None
	>>> c["foo"] = 20
	>>> c["foo"]
	20
	"""
	def __init__(self, row):
		self.row = row
		self.precomputed = {}

	def __str__(self):
		return "<<%s>>"%self.row
	
	def __repr__(self):
		return str(self)

	def __getitem__(self, indexSpec):
		try:
			if indexSpec in self.precomputed:
				return self.precomputed[indexSpec]
			if "-" in indexSpec:
				start, end = [int(s) for s in indexSpec.split("-")]
				val = self.row[start-1:end].strip()
			else:
				val = self.row[int(indexSpec)-1].strip()
			self.precomputed[indexSpec] = val or None
			return val or None
		except (IndexError, ValueError):
			raise KeyError(indexSpec)

	def get(self, key, default=None):
		try:
			val = self[key]
		except KeyError:
			val = default
		return val

	def __setitem__(self, key, value):
		self.precomputed[key] = value


class ColumnGrammar(grammar.Grammar):
	"""is a grammar has character ranges like 10-12 as row preterminals.

	These never call any documentHandler (use REGrammars if you need
	this).	You can, however, ignore a couple of lines at the head.

	The row production of these grammars always is just a (text) line.

	_iterRows will return magic objects.  These magic object return
	row[start-1:end] if asked for the item "<start>:<end>".  They will
	return None if the matched string is empty.  Otherwise, they
	behave like rowdicts should (i.e., you can set values).
	"""
	def __init__(self):
		grammar.Grammar.__init__(self, {
			"topIgnoredLines": 0,
			"booster": None,
		})

	def _iterRows(self):
		for i in range(int(self.get_topIgnoredLines())):
			self.inputFile.readline()
		while True:
			ln = self.inputFile.readline()
			if not ln:
				break
			yield ColumnExtractor(ln[:-1])

	def _getDocumentRow(self):
		return {}

	def _tryBooster(self, inputFile, tableName="ppmx.data"):
		from gavo import config
		import os
		if isinstance(inputFile, file):
			inputFile = inputFile.name
		host, port, dbname = config.settings.get_db_dsn().split(":")
		connDesc = "host=%s port=%s user=%s password=%s dbname=%s\n"%(
			host, port, config.settings.get_db_user(), 
			config.settings.get_db_password(), dbname)
		booster = self.get_booster()
		if booster==None:
			raise BoosterNotDefined
		f = os.popen("%s '%s' '%s'"%(booster, inputFile, tableName), "w")
		f.write(connDesc)
		f.flush()
		retval = f.close()
		if retval!=None:
			retval = (retval&0xff00)<<16
		if retval==126: 
			raise BoosterNotAvailable("Invalid binary format")
		if retval==127:
			raise BoosterNotAvailable("Binary not found")
		if retval:
			raise BoosterFailed()

	def parse(self, inputFile):
		"""is overridden because we may want to run a booster here.
		"""
		try:
			self._tryBooster(inputFile)
		except BoosterNotDefined:
			Grammar.parse(self, inputFile)
		except BoosterNotAvailable, msg:
			gavo.ui.displayMessage("Column grammar defined, but booster not"
				" available (%s).  Running python code."%msg)
			Grammar.parse(self, inputFile)
		except BoosterFailed:
			raise gavo.Error("Booster failed, giving up")



def _test():
	import doctest, columngrammar
	doctest.testmod(columngrammar)


if __name__=="__main__":
	_test()
