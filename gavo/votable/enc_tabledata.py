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
			action = ("  tokens.append(%r)"%defaultNullValue)
	else:
		action = "  tokens.append(%r)"%nullvalue
	return [
			'if val is None:',
			action,
			'else:']+coding.indentList(src, "  ")


def _makeFloatEncoder(field):
	return _addNullvalueCode(field, [
		"if val!=val:",  # NaN is a null value, too
		"  tokens.append('')",
		"else:",
		"  tokens.append(repr(val))"],
		float, "")


def _makeComplexEncoder(field):
	return _addNullvalueCode(field, [
		"try:",
		"  tokens.append('%s %s'%(repr(val.real), repr(val.imag)))",
		"except AttributeError:",
		"  tokens.append(repr(val))",],
		common.validateTDComplex, "")


def _makeBooleanEncoder(field):
	return [
		"if val is None:",
		"  tokens.append('?')",
		"elif val:",
		"  tokens.append('1')",
		"else:",
		"  tokens.append('0')",]


def _makeIntEncoder(field):
	return _addNullvalueCode(field, [
		"tokens.append(str(val))"],
		int)


def _makeCharEncoder(field):
	return _addNullvalueCode(field, [
		"tokens.append(common.escapeCDATA(val))"],
		lambda _: True)


_encoders = {
	'boolean': _makeBooleanEncoder,
	'bit': _makeIntEncoder,
	'unsignedByte': _makeIntEncoder,
	'short': _makeIntEncoder,
	'int': _makeIntEncoder,
	'long': _makeIntEncoder,
	'char': _makeCharEncoder,
	'unicodeChar': _makeCharEncoder,
	'float': _makeFloatEncoder,
	'double': _makeFloatEncoder,
	'floatComplex': _makeComplexEncoder,
	'doubleComplex': _makeComplexEncoder,
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
