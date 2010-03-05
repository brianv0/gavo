"""
Binary VOTable encoding.
"""

import struct

from gavo.votable import coding
from gavo.votable import common


def _addNullvalueCode(field, nullvalue, src):
	"""adds code to let null values kick in a necessary.

	nullvalue here has to be a ready-made *python* literal.  Take care
	when passing in user supplied values here.
	"""
	if nullvalue is None:
		action = ("  raise common.BadVOTableData('None passed for field"
			" that has no NULL value', None, '%s')")%field.getDesignation()
	else:
		action = "  val = %s"%nullvalue
	return [
		'if val is None:',
		action,]+src


def _makeFloatEncoder(field):
	if field.a_datatype=="float":
		code = "!f"
	else:
		code = "!d"
	nullvalue = coding.getNullvalue(field, float)
	if nullvalue is None:
		nullvalue = "common.NaN"
	else:
		nullvalue = repr(float(nullvalue))
	return _addNullvalueCode(field, nullvalue,
		["tokens.append(struct.pack('%s', val))"%code])


_encoders = {
		"float": _makeFloatEncoder,
		"double": _makeFloatEncoder,
}

def getLinesFor(field):
	"""returns a sequence of python source lines to encode values described
	by field into tabledata.
	"""
	if field.a_arraysize in common.SINGLEVALUES:
		return _encoders[field.a_datatype](field)
	else:
		return _getArrayEncoderLines(field)


def getPostamble(tableDefinition):
	return [
		"return ''.join(tokens)"]


def getGlobals():
	return globals()
