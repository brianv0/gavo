"""
Coding and decoding from binary.
"""

import re
import traceback

from gavo.votable import coding
from gavo.votable import common


# literals for BINARY booleans
BINBOOL = {
	't': True,
	'1': True,
	'f': False,
	'0': False,
	'?': None,
}


def tokenizeComplexArr(val):
	"""iterates over suitable number literal pairs from val.
	"""
	last = None
	if val is None:
		return
	for item in val.split():
		if not item:
			continue
		if last is None:
			last = item
		else:
			yield "%s %s"%(last, item)
			last = None
	if last:
		yield last


def tokenizeBitArr(val):
	"""iterates over 0 or 1 tokens in val, discarding everything else.
	"""
	if val is None:
		return
	for item in val:
		if item in "01":
			yield item


def tokenizeNormalArr(val):
	"""iterates over all whitespace-separated tokens in val
	"""
	if val is None:
		return
	for item in val.split():
		if item:
			yield item


def _addNullvalueCode(field, src, validator):
	"""adds code to catch nullvalues if required by field.
	"""
	nullvalue = coding.getNullvalue(field, validator)
	if nullvalue:
		src = [
			'if val=="%s":'%nullvalue,
			'  row.append(None)',
			'else:']+coding.indentList(src, "  ")
	return src


def _makeFloatDecoder(field):
	src = [
		'if not val:',
		'  row.append(None)',
		'else:',
		'  row.append(float(val))',]
	return _addNullvalueCode(field, src, float)


def _makeComplexDecoder(field):
	src = [
		'if not val:',
		'  row.append(None)',
		'else:',
		'  try:',
		'    r, i = val.split()',
		'  except ValueError:',
		'    r, i = float(val), 0',
		'  if r!=r or i!=i:',
		'    row.append(None)',
		'  else:'
		'    row.append(complex(float(r), float(i)))',]
	return _addNullvalueCode(field, src, common.validateTDComplex)


def _makeIntDecoder(field, maxInt):
	src = [
		'if not val:',
		'  row.append(None)',
		'elif val.startswith("0x"):',
		'  unsigned = int(val[2:], 16)',
		# Python hex parsing is unsigned, fix manually based on maxInt
		'  if unsigned>=%d:'%maxInt,
		'    row.append(unsigned-%d)'%((maxInt+1)*2),
		'  else:',
		'    row.append(unsigned)',
		'else:',
		'  row.append(int(val))']
	return _addNullvalueCode(field, src, common.validateVOTInt)


def _makeCharDecoder(field, emptyIsNull=True):
	"""parseString enables return of empty string (as opposed to None).
	"""
# Elementtree already makes sure we're only seeing unicode strings here
	src = []
	if emptyIsNull:
		src.extend([
			'if not val:',
			'  val = None',])
	else:
		src.extend([
			'if val is None:',
			'  val = ""'])
	src.append('row.append(val)')
	return src


def _makeBooleanDecoder(field):
	return ['row.append(TDENCBOOL[input.read(1)])']


def _makeBitDecoder(field):
	return ['row.append(int(val))']


_decoders = {
	'boolean': _makeBooleanDecoder,
#	'bit': _makeBitDecoder,
#	'unsignedByte': lambda v: _makeIntDecoder(v, 256),
#	'char': _makeCharDecoder,
#	'unicodeChar': _makeCharDecoder,  # heavy lifting done by the xml parser
#	'short': lambda v: _makeIntDecoder(v, 32767),
#	'int': lambda v: _makeIntDecoder(v, 2147483647),
#	'long': lambda v: _makeIntDecoder(v, 9223372036854775807L),
#	'float': _makeFloatDecoder,
#	'double': _makeFloatDecoder,
#	'floatComplex': _makeComplexDecoder,
#	'doubleComplex': _makeComplexDecoder,
}

def _getArrayDecoderLines(field):
	"""returns lines that decode arrays of literals.

	Unfortunately, the spec is plain nuts, so we need to pull some tricks here.

	We completely ignore any arraysize specification here.
	"""
	type, arraysize = field.a_datatype, field.a_arraysize
	if type=='char' or type=='unicodeChar':
		return _makeCharDecoder(field, emptyIsNull=False)
	src = [ # OMG.  I'm still hellbent on not calling functions here.
		'arrayLiteral = val',
		'fullRow, row = row, []',
		]
	if type=='floatComplex' or type=='doubleComplex':
		src.append("for val in tokenizeComplexArr(arrayLiteral):")
	elif type=='bit':
		src.append("for val in tokenizeBitArr(arrayLiteral):")
	else:
		src.append("for val in tokenizeNormalArr(arrayLiteral):")
	src.extend(coding.indentList(_decoders[type](field), "  "))
	src.append("fullRow.append(row)")
	src.append("row = fullRow")
	return src


def getLinesFor(field):
	"""returns a sequence of python source lines to decode BINARY-encoded
	values for field.
	"""
	if field.a_arraysize not in common.SINGLEVALUES:
		return _getArrayDecoderLines(field)
	return _decoders[field.a_datatype](field)


def getPostamble(tableDefinition):
	return [
		"return row"]


def getGlobals():
	return globals()
