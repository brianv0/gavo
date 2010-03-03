"""
Coding and decoding from tabledata.
"""

import re

from gavo.votable import coding


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
		'  row.append(complex(float(r), float(i)))',]
	def validateComplex(val):
		re, im = map(float, val.split())
	return _addNullvalueCode(field, src, validateComplex)


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
	return _addNullvalueCode(field, src, int)


def _makeCharDecoder(field):
# Elementtree already makes sure we're only seeing unicode strings here
	return [
		'if not val:',
		'  val = None',
		'row.append(val)']


def _makeBooleanDecoder(field):
	return ['row.append(TDENCBOOL[val.strip().lower()])']


def _makeBitDecoder(field):
	return ['row.append(int(val))']


_decoders = {
	'boolean': _makeBooleanDecoder,
	'bit': _makeBitDecoder,
	'unsignedByte': lambda v: _makeIntDecoder(v, 256),
	'char': _makeCharDecoder,
	'unicodeChar': _makeCharDecoder,  # heavy lifting done by the xml parser
	'short': lambda v: _makeIntDecoder(v, 32767),
	'int': lambda v: _makeIntDecoder(v, 2147483647),
	'long': lambda v: _makeIntDecoder(v, 9223372036854775807L),
	'float': _makeFloatDecoder,
	'double': _makeFloatDecoder,
	'floatComplex': _makeComplexDecoder,
	'doubleComplex': _makeComplexDecoder,
}

def getDecoderLines(field):
	"""returns a sequence of python source lines to decode TABLEDATA-encoded
	values for field.
	"""
	if field.a_arraysize not in coding.SINGLEVALUES:
		return _getArrayDecoderLines(field)
	return _decoders[field.a_datatype](field)
