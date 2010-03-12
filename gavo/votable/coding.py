"""
Common code for coding and decoding VOTable table data.
"""

from gavo import utils
from gavo.votable import common
from gavo.votable.model import VOTable


def getRowEncoderSource(tableDefinition, encoderModule):
	"""returns the source for a function encoding rows of tableDefition
	in the format implied encoderModule

	tableDefinition is a VOTable.TABLE instance, encoderModule
	is one of the enc_whatever modules (this function needs getLinesFor
	and getPostamble from them).
	"""

	source = [
		"def codec(tableRow):", 
		"  tokens = []",
		"  val = None"]
	for index, field in enumerate(
			tableDefinition.iterChildrenOfType(VOTable.FIELD)):
		source.extend([
			"  try:",
			"    val = tableRow[%d]"%index])
		source.extend(indentList(encoderModule.getLinesFor(field), "    "))
		source.extend([
			"  except common.VOTableError:",
			"    raise",
			"  except Exception, ex:",
			"    traceback.print_exc()",
			"    raise common.BadVOTableData(unicode(ex), val, '%s')"%
				field.getDesignation()])
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
	#print(source)
	try:
		exec source in ns
	except:
		import sys, traceback
		sys.stderr.write("Oomph, internal error.  Source:\n")
		sys.stderr.write(source)
		traceback.print_exc()
		sys.exit("")
	return ns["codec"]


def buildEncoder(tableDefinition, encoderModule):
	return buildCodec(
		getRowEncoderSource(tableDefinition, encoderModule),
		encoderModule.getGlobals())


def buildDecoder(tableDefinition, decoderModule):
	return buildCodec(
		decoderModule.getRowDecoderSource(tableDefinition),
		decoderModule.getGlobals())


def indentList(lines, indent):
	"""prepens indent to all elements in lines.
	"""
	return [indent+l for l in lines]


def getNullvalue(field, validator, default=None):
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
	if nullvalue is None:
		return default
	else:
		_ = validator(nullvalue)
	return nullvalue


def trim(seq, arraysize, padder):
	"""returns seq with length arraysize.

	arraysize is interpreted as an int (and thus must not be '*'
	or anything like that).  If seq is shorter, padder*missing will
	be appended, if it is longer, seq will be shortened from the end.

	This is intended as a helper for array encoders.
	"""
	goal = int(arraysize)
	if len(seq)<goal:
		seq = seq+padder*(goal-len(seq))
	elif len(seq)>goal:
		seq = seq[:goal]
	return seq
