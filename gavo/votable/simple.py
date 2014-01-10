"""
A simplified API to single-table VOTables.

The basic idea is: open(...) -> (table, metadata),

where table is a numpy array.
"""

#c Copyright 2008-2014, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


try:
	import numpy
	from numpy import rec

	# map from VOTable datatypes to numpy type designators:
	numpyType = {
		"short": numpy.int16,
		"int": numpy.int32,
		"long": numpy.int64,
		"float": numpy.float32,
		"double": numpy.float64,
		"boolean": numpy.bool,
		"char": str,
		"floatComplex": numpy.complex64,
		"doubleComplex": numpy.complex128,
		"unsignedByte": numpy.uint8,
		"unicodeChar": numpy.unicode_
	}
except ImportError:
	# keep numpy optional
	pass

from gavo.votable import parser
from gavo.votable import tablewriter
from gavo.votable.model import VOTable as V



class TableMetadata(object):
	"""Metadata for a VOTable table instance, i.e., column definitions, groups,
	etc.

	These are constructed with a VOTable TABLE instance and infos, a dictionary
	mapping info names to lists of V.INFO items.
	"""
	def __init__(self, tableElement, infos):
		self.votTable = tableElement
		self.infos = infos
		self.fields = list(tableElement.iterChildrenOfType(V.FIELD))

	def __iter__(self):
		return iter(self.fields)
	
	def __len__(self):
		return len(self.fields)
	
	def __getitem__(self, index):
		return self.fields[index]

	def getFields(self):
		return self.votTable.getFields()
	
	def iterDicts(self, data):
		"""iterates over data, but returns each row as a dict.

		data is a result set as returned by load.
		"""
		names = [f.name for f in self]
		for row in data:
			yield dict(zip(names, row))


def makeDtype(tableMetadata):
	"""returns an record array datatype for a given table metadata.
	"""
	dtypes = []
	seen = set()
	for f in tableMetadata:
		name = f.getDesignation().encode('ascii', 'ignore')
		while name in seen:
			name = name+"_"
		seen.add(name)
		shape = f.getShape()
		if shape is None:
			dtypes.append((name, numpyType[f.datatype]))
		else:
			dtypes.append((
				name,
				numpyType[f.datatype],
				shape))
	return dtypes


def load(source):
	"""returns (data, metadata) from the first table of a VOTable.

	data is a list of records (as a list), metadata a TableMetadata instance.

	source can be a string that is then interpreted as a local file name,
	or it can be a file-like object.
	"""
	if isinstance(source, basestring):
		source = file(source)
	infos = {}

	# the following loop is a bit weird since we want to catch info items
	# after the table and thus only exit the loop when the next table starts
	# or the iterator is exhausted.
	rows = None
	for element in parser.parse(source, [V.INFO]):
		if isinstance(element, V.INFO):
			infos.setdefault(element.name, []).append(element)
		else:
			if rows is not None:
				break
			fields = TableMetadata(element.tableDefinition, infos)
			rows = list(element)
	if rows is None: # No table included
		return None, None
	return rows, fields


def save(data, tableDef, destF):
	"""saves (data, tableDef) in VOTable format to destF.

	data is a sequence of tuples, tableDef V.TABLE instance as, for example,
	obtainable from metadata.votTable as returned by load.  data must contain
	type-right python values that match the table definition.

	A load-save cycle loses all top-level and resource level metadata in the
	simplified interface.  Use the full interface if that hurts you.
	"""
	root = V.VOTABLE[
		V.RESOURCE[
			tablewriter.DelayedTable(tableDef, data, V.BINARY)]]
	tablewriter.write(root, destF)
