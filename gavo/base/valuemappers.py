"""
Serialising table rows.

The main class in this module is the SerManager, which knows about
a target table and figures out how to turn the values in the table
rows into strings.

This is used by formats.votablewrite and the HTML table serialisation.

utils.serializers has once been a part of this module.  To save migration
effort, for now it reproduces that module's interface.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import re

from gavo import adql
from gavo import utils
from gavo.utils.serializers import ( #noflake: for (compatibility) export
	ValueMapperFactoryRegistry, defaultMFRegistry, AnnotatedColumn, 
	registerDefaultMF)

__docformat__ = "restructuredtext en"


class SerManager(utils.IdManagerMixin):
	"""A wrapper for the serialisation of table data.

	SerManager instances keep information on what values certain columns can
	assume and how to map them to concrete values in VOTables, HTML or ASCII.
	
	They are constructed with a BaseTable instance.

	You can additionally give:

		- withRanges -- ignored, going away
		- acquireSamples -- ignored, going away
		- idManager -- an object mixing in utils.IdManagerMixin.  This is important
			if the ids we are assigning here end up in a larger document.  In that
			case, pass in the id manager of that larger document.  Default is the
			SerManager itself
		- mfRegistry -- a map factory registry.  Default is the defaltMFRegistry,
		  which is suitable for VOTables.
	
	Iterate over a SerManager to retrieve the annotated columns.
	"""
	# Filled out on demand
	_nameDict = None

	def __init__(self, table, withRanges=True, acquireSamples=True,
			idManager=None, mfRegistry=defaultMFRegistry):
		self.table = table
		if idManager is not None:
			self.cloneFrom(idManager)
		self.notes = {}
		self._makeAnnotatedColumns()
		self._makeMappers(mfRegistry)
	
	def __iter__(self):
		return iter(self.annCols)

	def _makeAnnotatedColumns(self):
		self.annCols = []
		for column in self.table.tableDef:
			self.annCols.append(
				AnnotatedColumn(column, self.table.votCasts.get(column.name)))

			# We unconditionally generate IDs for FIELDs since rev ~4368
			# If a column actually got included twice in a VOTable, its id
			# would occur twice in the VOTable; I guess that would need
			# handling in xmlstan
			colId = self.getOrMakeIdFor(column, column.id or column.key)
			if colId is not None:
				self.annCols[-1]["id"] = colId

			# if column refers to a note, remember the note
			if column.note:
				try:
					self.notes[column.note.tag] = column.note
					self.annCols[-1]["note"] = column.note
				except (ValueError, utils.NotFoundError): 
					pass # don't worry about missing notes, but don't display them either
	
		self.byName = dict(
			(annCol["name"], annCol) for annCol in self.annCols)

	def _makeMappers(self, mfRegistry):
		"""returns a sequence of functions mapping our columns.

		As a side effect, column properties may change (in particular,
		datatypes).
		"""
		self.mappers = tuple(mfRegistry.getMapper(annCol) for annCol in self)

	def getColumnByName(self, name):
		return self.byName[name]

	def _compileMapFunction(self, funcLines):
		"""helps _make(Dict|Tuple)Factory.
		"""
		return utils.compileFunction(
			"\n".join(funcLines), "buildRec",
			useGlobals=dict(("map%d"%index, mapper) 
				for index, mapper in enumerate(self.mappers)))

	def _makeDictFactory(self):
		"""returns a function that returns a dictionary of mapped values
		for a row dictionary.
		"""
		colLabels = [str(c["name"]) for c in self]
		funDef = ["def buildRec(rowDict):"]
		for index, label in enumerate(colLabels):
			if self.mappers[index] is not utils.identity:
				funDef.append("\trowDict[%r] = map%d(rowDict[%r])"%(
					label, index, label))
		funDef.append("\treturn rowDict")
		return self._compileMapFunction(funDef)

	def _makeTupleFactory(self):
		"""returns a function that returns a tuple of mapped values
		for a row dictionary.
		"""
		funDef = ["def buildRec(rowDict):", "\treturn ("]
		for index, cd in enumerate(self):
			if self.mappers[index] is utils.identity:
				funDef.append("\t\trowDict[%r],"%cd["name"])
			else:
				funDef.append("\t\tmap%d(rowDict[%r]),"%(index, cd["name"]))
		funDef.append("\t)")
		return self._compileMapFunction(funDef)

	def _iterWithMaps(self, buildRec):
		"""helps getMapped(Values|Tuples).
		"""
		colLabels = [f.name for f in self.table.tableDef]
		if not colLabels:
			yield ()
			return
		for row in self.table:
			yield buildRec(row)

	def getMappedValues(self):
		"""iterates over the table's rows as dicts with mapped values.
		"""
		return self._iterWithMaps(self._makeDictFactory())

	def getMappedTuples(self):
		"""iterates over the table's rows as tuples with mapped values.
		"""
		return self._iterWithMaps(self._makeTupleFactory())


def needsQuoting(identifier, forRowmaker=False):
	"""returns True if identifier needs quoting in an SQL statement.
	>>> needsQuoting("RA(J2000)")
	True
	>>> needsQuoting("ABS")
	True
	>>> needsQuoting("r")
	False
	"""
	if utils.identifierPattern.match(identifier) is None:
		return True
	# extra rule for standards SQL 92
	if identifier.startswith("_"):
		return True

	if identifier.lower() in getNameBlacklist(forRowmaker):
		return True
	return False


@utils.memoized
def getNameBlacklist(forRowmaker=False):
	"""returns a set of names not suitable for table column names.

	This comprises SQL reserved words in lower case and, if forRowmaker
	is true, also some names damaging row makers (e.g. python reserved
	words).
	"""
	res = set(k.lower() for k in adql.allReservedWords)
	if forRowmaker:
		import keyword
		from gavo.rscdef import rmkfuncs
		res = (res 
			| set(["result_", "rowdict_"])
			| set(k.lower() for k in keyword.kwlist)
			| set(k.lower() for k in dir(rmkfuncs)))
	return frozenset(res)


class VOTNameMaker(object):
	"""A class for generating db-unique names from VOTable fields.

	This is important to avoid all kinds of weird names the remaining
	infrastructure will not handle.  "Normal" TableDefs assume unquoted
	SQL identifiers as names, and want all names unique.

	Using this class ensures these expectations are met in a reproducible
	way (i.e., given the same table, the same names will be assigned).
	"""
	def __init__(self):
		self.knownNames, self.index = set(getNameBlacklist(True)), 0

	def makeName(self, field):
		preName = re.sub("[^\w]+", "x", (getattr(field, "name", None) 
			or getattr(field, "ID", None)
			or "field%02d"%self.index))
		if not re.match("[A-Za-z_]", preName):
			preName = "col_"+preName
		while preName.lower() in self.knownNames:
			preName = preName+"_"
		self.knownNames.add(preName.lower())
		self.index += 1
		return preName


def _test():
	import doctest, valuemappers
	doctest.testmod(valuemappers)


if __name__=="__main__":
	_test()

