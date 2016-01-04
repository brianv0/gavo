"""
Commands for obtaining information about various things in the data center.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import api
from gavo import base
from gavo import svcs
from gavo import utils
from gavo.imp.argparse import ArgumentParser

NUMERIC_TYPES = frozenset(["smallint", "integer", "bigint", "real",
	"double precision"])

ORDERED_TYPES = frozenset(["timestamp", "text", "unicode"]) | NUMERIC_TYPES


class AnnotationMaker(object):
	"""A class for producing column annotations.
	
	An annotation simply is a dictionary with some well-known keys.  They
	are generated from DB queries.  It is this class' responsibility
	to collect the DB query result columns pertaining to a column and
	produce the annotation dictionary from them.

	To make this happen, it is constructed with the column; then, for
	each property queried, addPropertyKey is called.  Finally, addAnnotation
	is called with the DB result row (see annotateDBTable) to actually
	make and attach the dictionary.
	"""
	def __init__(self, column):
		self.column = column
		if not hasattr(self.column, "annotations"):
			self.column.annotations = {}
		self.propDests = {}

	def doesWork(self):
		return self.propDests

	def getOutputFieldFor(self, propName, propFunc, nameMaker):
		"""returns an OutputField that will generate a propName annotation
		from the propFunc function.

		propFunc for now has a %(name)s where the column name must be
		inserted.

		nameMaker is something like a base.VOTNameMaker.
		"""
		destCol = nameMaker.makeName(propName+"_"+self.column.name)
		self.propDests[destCol] = propName
		return api.makeStruct(svcs.OutputField,
			name=destCol, 
			select=propFunc%{"name": self.column.name}, 
			type=self.column.type)

	def annotate(self, resultRow):
		"""builds an annotation of the column form resultRow.

		resultRow is a dictionary containing values for all keys registred
		through addPropertyKey.

		If the column already has an annotation, only the new keys will be
		overwritten.
		"""
		for srcKey, destKey in self.propDests.iteritems():
			self.column.annotations[destKey] = resultRow[srcKey]


def annotateDBTable(td, extended=True, requireValues=False):
	"""returns the TableDef td with domain annotations for its columns.

	td must be an existing on-Disk table.

	The annotations come in a dictionary-valued attribute on each
	column annotated.  Possible keys include "min", "max", "avg", and "hasnulls".
	Only columns with the appropriate types (i.e., orderable, and, 
	for avg, numeric) are annotated.

	Without extended, only min and max are annotated.  With
	requireValues, only numeric columns that already have a values child
	are annotated.
	"""
	outputFields, annotators = [], []
	nameMaker = base.VOTNameMaker()
	for col in td:
		annotator = AnnotationMaker(col)

		if col.type in ORDERED_TYPES or col.type.startswith("char"):
			if requireValues:
				if (col.type not in NUMERIC_TYPES 
						or not col.values
						or col.values.min is None):
					continue

			outputFields.append(annotator.getOutputFieldFor("max",
				"MAX(%(name)s)", nameMaker))
			outputFields.append(annotator.getOutputFieldFor("min",
				"MIN(%(name)s)", nameMaker))
		
		if extended:
			if col.type in NUMERIC_TYPES:
				outputFields.append(annotator.getOutputFieldFor("avg",
					"AVG(%(name)s)", nameMaker))
			

			outputFields.append(annotator.getOutputFieldFor("hasnulls",
					"BOOL_OR(%(name)s IS NULL)", nameMaker))

		if annotator.doesWork():
			annotators.append(annotator)

	table = api.TableForDef(td)

	if not hasattr(table, "iterQuery"):
		raise api.ReportableError("Table %s cannot be queried."%td.getQName(),
			hint="This is probably because it is an in-memory table.  Add"
			" onDisk='True' to make tables reside in the database.")

	resultRow = list(table.iterQuery(outputFields, ""))[0]
	for annotator in annotators:
		annotator.annotate(resultRow)


_PROP_SEQ = ("min", "avg", "max", "hasnulls")

def printTableInfo(td):
	"""tries to obtain various information on the properties of the
	database table described by td.
	"""
	annotateDBTable(td)
	propTable = [("col",)+_PROP_SEQ]
	for col in td:
		row = [col.name]
		for prop in _PROP_SEQ:
			if prop in col.annotations:
				row.append(utils.makeEllipsis(
					utils.safe_str(col.annotations[prop]), 30))
			else:
				row.append("-")
		propTable.append(tuple(row))
	print utils.formatSimpleTable(propTable)


def parseCmdline():
	parser = ArgumentParser(
		description="Displays various stats about the table referred to in"
			" the argument.")
	parser.add_argument("tableId", help="Table id (of the form rdId#tableId)")
	return parser.parse_args()


def main():
	args = parseCmdline()
	td = api.getReferencedElement(args.tableId, api.TableDef)
	printTableInfo(td)
