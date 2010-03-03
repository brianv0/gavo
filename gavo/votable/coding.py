"""
Common code for coding and decoding VOTable table data.
"""

from gavo import utils
from gavo.votable import common
from gavo.votable.model import VOTable


# Values we accept as meaning "single value" in a FIELD's arraysize
SINGLEVALUES = set([None, '', '1'])

# literals for TDENC booleans
TDENCBOOL = {
	't': True,
	'1': True,
	'true': True,
	'f': False,
	'0': False,
	'false': False,
	'?': None,
	'': None,
}


def makeRowDecoder(tableDefinition, getDecoderLines):
	"""returns a compiled function taking raw data from a tableDefintion table
	and returning a python list.

	getDecoderLines is a function taking a model.FIELD instance and returning
	source code lines (no base indent) that append a value for
	that field to a list called row.
	"""
	source = ["def decodeRow(rawRow):", "  row = []"]
	for index, field in enumerate(
			tableDefinition.iterChildrenOfType(VOTable.FIELD)):
		source.append("  try:")
		source.append("    val = rawRow[%d]"%index)
		source.extend(indentList(getDecoderLines(field), "    "))
		source.append("  except:")
		source.append("    raise common.BadVOTableLiteral('%s', val)"%
			field.a_datatype)
	source.append("  return row")
	ns = {}
	ns.update(globals())
	source = "\n".join(source)
	try:
		exec source in ns
	except:
		import sys, traceback
		sys.stderr.write("Oomph, internal error.  Source:\n")
		sys.stderr.write(source)
		traceback.print_exc()
		sys.exit("")
	return ns["decodeRow"]


def indentList(lines, indent):
	"""prepens indent to all elements in lines.
	"""
	return [indent+l for l in lines]


def getNullvalue(field, validator):
	"""returns None or the nullvalue defined for field.

	validator is a function that raises some exception if the nullvalue
	is inappropriate.  It should do so in particular on everything that
	contains quotes and such; the nullvalues are included in source code
	and thus might be used to inject code if not validated.
	"""
	nullvalue = None
	for values in field.iterChildrenOfType(VOTable.VALUES):
		if values.a_null is not None:
			nullvalue = values.a_null
	if nullvalue is not None:
		_ = validator(nullvalue)
	return nullvalue
