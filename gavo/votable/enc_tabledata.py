"""
Encoding to tabledata.
"""

import traceback

from gavo.votable import coding
from gavo.votable import common


def _addNullvalueCode(field, src, validator, defaultNullValue=None):
	"""adds code handle null values where not default representation exists.
	"""
	nullvalue = coding.getNullvalue(field, validator)
	if nullvalue is None:
		if defaultNullValue is None:
			action = ("  raise common.BadVOTableData('None passed for field"
				" that has no NULL value', None, '%s')")%field.getDesignation()
		else:
			action = ("  row.append(%r)"%defaultNullValue)
	else:
		action = "  row.append(%r)"%nullvalue
	return [
			'if val is None:',
			action,
			'else:']+coding.indentList(src, "  ")


def _makeFloatEncoder(field):
	src = [
		"if val is None or val!=val:",  # NaN is a null value, too
		"  tokens.append('')",
		"else:",
		"  tokens.append(repr(val))"]
	return src


_encoders = {
	'float': _makeFloatEncoder,
	'double': _makeFloatEncoder,
}


def getLinesFor(field):
	"""returns a sequence of python source lines to encode values described
	by field into tabledata.
	"""
	return _encoders[field.a_datatype](field)


def getPostamble(tableDefinition):
	return [
		"return '<TR>%s</TR>'%(''.join('<TD>%s</TD>'%v for v in tokens))"]


def getGlobals():
	return globals()
