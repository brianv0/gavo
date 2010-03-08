"""
Binary VOTable encoding.
"""

import struct
import traceback

from gavo.votable import coding
from gavo.votable import common


floatNaN = struct.pack("!f", common.NaN)
doubleNaN = struct.pack("!d", common.NaN)


def _addNullvalueCode(field, nullvalue, src):
	"""adds code to let null values kick in a necessary.
 
	nullvalue here has to be a ready-made *python* literal.  Take care
	when passing in user supplied values here.
	"""
	if nullvalue is None:
		action = ("  raise common.BadVOTableData('None passed for field"
			" that has no NULL value', None, '%s')")%field.getDesignation()
	else:
		action = "  tokens.append(%s)"%nullvalue
	return [
		"if val is None:",
		action,
		"else:"
		]+coding.indentList(src, "  ")


def _makeBooleanEncoder(field):
	return [
		"if val is None:",
		"  tokens.append('?')",
		"elif val:",
		"  tokens.append('1')",
		"else:",
		"  tokens.append('0')",
	]


def _makeBitEncoder(field):
	# bits and bit arrays are just (possibly long) integers
	return [
		"if val is None:",
		"  raise common.BadVOTableData('Bits have no NULL value', None,",
		"    '%s')"%field.getDesignation(),
		"tmp = []",
		"curByte, rest = val%256, val//256",
		"while curByte:",
		"  tmp.append(chr(curByte))",
		"  curByte, rest = rest%256, rest//256",
		"tmp.reverse()",
		"if tmp:",
		"  tokens.append(struct.pack('%ds'%len(tmp), ''.join(tmp)))",
		"else:",
		"  tokens.append(struct.pack('B', 0))"]


def _generateFloatEncoderMaker(fmtCode, nullName):
	def makeFloatEncoder(field):
		return [
			"if val is None:",
			"  tokens.append(%s)"%nullName,
			"else:",
			"  tokens.append(struct.pack('%s', val))"%fmtCode]
	return makeFloatEncoder


def _generateComplexEncoderMaker(fmtCode, singleNull):
	def makeComplexEncoder(field):
		return [
			"if val is None:",
			"  tokens.append(%s+%s)"%(singleNull, singleNull),
			"else:",
			"  tokens.append(struct.pack('%s', val.real, val.imag))"%fmtCode]
	return makeComplexEncoder


def _generateIntEncoderMaker(fmtCode):
	def makeIntEncoder(field):
		nullvalue = coding.getNullvalue(field, int)
		if nullvalue is not None:
			nullvalue = repr(struct.pack(fmtCode, int(nullvalue)))
		return _addNullvalueCode(field, nullvalue,[
			"tokens.append(struct.pack('%s', val))"%fmtCode])
	return makeIntEncoder


def _makeCharEncoder(field):
	nullvalue = coding.getNullvalue(field, lambda _: True)
	if nullvalue is not None:
		nullvalue = repr(struct.pack("c", nullvalue))
	return _addNullvalueCode(field, nullvalue, [
		"tokens.append(struct.pack('c', val))"])


def _makeUnicodeCharEncoder(field):
	nullvalue = coding.getNullvalue(field, lambda _: True)
	if nullvalue is not None:
		coded = nullvalue.encode("utf-16be")
		nullvalue = repr(struct.pack("%ds"%len(coded), coded))
	return _addNullvalueCode(field, nullvalue, [
		"coded = val.encode('utf-16be')",
		"tokens.append(struct.pack('%ds'%len(coded), coded))"])


_encoders = {
		"boolean": _makeBooleanEncoder,
		"bit": _makeBitEncoder,
		"unsignedByte": _generateIntEncoderMaker('B'),
		"short": _generateIntEncoderMaker('!h'),
		"int": _generateIntEncoderMaker('!i'),
		"long": _generateIntEncoderMaker('!q'),
		"char": _makeCharEncoder,
		"unicodeChar": _makeUnicodeCharEncoder,
		"double": _generateFloatEncoderMaker("!d", "doubleNaN"),
		"float": _generateFloatEncoderMaker("!f", "floatNaN"),
		"doubleComplex": _generateComplexEncoderMaker("!dd", "doubleNaN"),
		"floatComplex": _generateComplexEncoderMaker("!ff", "floatNaN"),
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
