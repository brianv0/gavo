"""
BINARY2 VOTable decoding

BINARY2 is like BINARY, except every record is preceded by a mask which
columns are NULL.

Sorry for gratuituously peeking into the guts of dec_binary here.  But well,
it's family.
"""

import re
import struct
import traceback

from gavo.votable import coding
from gavo.votable import common
from gavo.votable.dec_binary import *
from gavo.votable.model import VOTable


def getRowDecoderSource(tableDefinition):
	"""returns the source for a function deserializing a BINARY stream.

	tableDefinition is a VOTable.TABLE instance.  The function returned
	expects a file-like object.
	"""
	source = [
		"def codec(inF):", 
		"  row = []",
		"  nullMap = nullFlags.getFromFile(inF)"]

	for index, field in enumerate(
			tableDefinition.iterChildrenOfType(VOTable.FIELD)):
		source.extend([
			"  try:",]+
			coding.indentList(getLinesFor(field), "    ")+[
			"  except IOError:",  # EOF on empty row is ok.
			"    if inF.atEnd and row==[]:",
			"      return None",
			"    raise",
			"  except:",
			"    traceback.print_exc()",
			"    raise common.BadVOTableLiteral('%s', repr(inF.lastRes))"%(
				field.datatype),
			"  if nullMap.pop():",
			"    row[-1] = None",
			])
	source.append("  return row")
	return "\n".join(source)


def getGlobals(tableDefinition):
	vars = globals()
	vars["nullFlags"] = common.NULLFlags(len(tableDefinition.getFields()))
	return vars
