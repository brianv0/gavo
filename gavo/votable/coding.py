"""
Common code for coding and decoding VOTable table data.
"""

from gavo import utils
from gavo.votable import common
from gavo.votable.model import VOTable


def getRowDecoderSource(tableDefinition, decoderModule):
	"""returns the source for a function decoding rows of tableDefition
	encoded in the format implied by decoderModule.

	tableDefinition is a VOTable.TABLE instance, decoderModule
	is a function from one of the dec_XXX modules.
	"""
	source = ["def decodeRow(rawRow):", "  row = []"]
	for index, field in enumerate(
			tableDefinition.iterChildrenOfType(VOTable.FIELD)):
		source.append("  try:")
		source.append("    val = rawRow[%d]"%index)
		source.extend(indentList(decoderModule.getLinesFor(field), "    "))
		source.append("  except:")
		source.append("    traceback.print_exc()")
		source.append("    raise common.BadVOTableLiteral('%s', val)"%
			field.a_datatype)
	source.extend(indentList(
		decoderModule.getPostamble(tableDefinition), "  "))
	return "\n".join(source)


def getRowEncoderSource(tableDefinition, encoderModule):
	"""returns the source for a function encoding rows of tableDefition
	in the format implied by encoderModule.

	tableDefinition is a VOTable.TABLE instance, encoderModule
	is one of the enc_XXX modules.
	"""

	source = ["def encodeRow(tableRow):", "	tokens = []"]
	for index, field in enumerate(
			tableDefinition.iterChildrenOfType(VOTable.FIELD)):
		source.append("  try:")
		source.append("    val = tableRow[%d]"%index)
		source.extend(indentList(encoderModule.getLinesFor(field), "    "))
		source.append("  except common.VOTableError:")
		source.append("    raise")
		source.append("  except Exception, ex:")
		source.append("    traceback.print_exc()")
		source.append("    raise common.BadVOTableData('%s', val, unicode(ex))"%
			field.getDesignation)
	source.extend(indentList(
		encoderModule.getPostamble(tableDefinition), "  "))
	return "\n".join(source)


def buildCodec(source, env):
	"""returns a compiled function for source in env.

	Source is the result of one of the makeXXX functions in this module,
	env typically the result of a getGlobals() on the codec module.
	"""
	ns = {}
	ns.update(env)
#	print(source)
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
