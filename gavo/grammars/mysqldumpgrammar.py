"""
A q'n'd grammar for reading MySQL dumps of moderate size.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import re

from gavo import base
from gavo.grammars import common


def guessFieldNames(dump):
	"""returns the table name and the column names for the first 
	CREATE TABLE statement in a MySQL dump.
	"""
	mat = re.search("CREATE TABLE `([^`]*)` \(", dump)
	if not mat:
		raise base.DataError("No proper CREATE TABLE statement found")
	tableName = mat.group(1)
	curPos = mat.end()
	names = []
	
	rowPat = re.compile(
		r"\s*`(?P<name>[^`]*)` (?P<type>[^ ]*) (?P<flags>[^,)]*),?")
	while True:
		mat = rowPat.match(dump, curPos)
		if not mat:
			# sanity check would be great here.
			break
		names.append(mat.group("name"))
		curPos = mat.end()

	return tableName, names, curPos
	

def makeRecord(fieldNames, fieldValues):
	"""creates a rawdict for fieldValues

	This function should undo any quoting introduced by MySQL.  It doesn't right
	now since we're not working from actual docs.
	"""
	res = {}
	for name, val in zip(fieldNames, fieldValues):
		if val=="NULL":
			val = None
		else:
			val = val.strip("'")
		res [name] = val
	return res


class RowIterator(common.FileRowIterator):
	def _iterRows(self):
		dumpContents = self.inputFile.read()

		tableName, fieldNames, curPos = guessFieldNames(dumpContents)
		insertionPat = re.compile("INSERT INTO `%s` VALUES "%tableName)

		# TODO: handle embedded quotes ('')
		valueRE = "('[^']*'|[^',][^,]*)"
		rowPat = re.compile(r"\s*\(%s\),?"%(",".join(valueRE for i in fieldNames)))

		while True:
			mat = insertionPat.search(dumpContents, curPos)
			if not mat:
				break
			curPos = mat.end()


			while True:
				mat = rowPat.match(dumpContents, curPos)
				if not mat:
					# sanity check that we really reached the end of the VALUE
					# statement
					if not dumpContents[curPos:curPos+30].strip().startswith(";"):
						raise base.DataError("Expected VALUES-ending ; char %s;"
							" found %s instead."%(
								curPos, repr(dumpContents[curPos: curPos+30])))
					break

				yield makeRecord(fieldNames, mat.groups())
				curPos = mat.end()



class MySQLDumpGrammar(common.Grammar, common.FileRowAttributes):
	"""A grammar pulling information from MySQL dump files.

	WARNING: This is a quick hack.  If you want/need it, please contact the
	authors.

	At this point this is nothing but an ugly RE mess with lots of assumptions
	about the dump file that's easily fooled.  Also, the entire dump file
	will be pulled into memory.

	Since grammar semantics cannot do anything else, this will always only
	iterate over a single table.  This currently is fixed to the first,
	but it's conceivable to make that selectable.

	Database NULLs are already translated into Nones.

	In other words: It might do for simple cases.  If you have something else,
	improve this or complain to the authors.
	"""
	name_ = "mySQLDumpGrammar"
	rowIterator = RowIterator
