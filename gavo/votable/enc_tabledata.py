"""
Coding and decoding from tabledata.
"""

import re

from gavo.votable import coding


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
	nullvalue = coding.getNullvalue(field, int)
	if nullvalue:
		src = [
			'if val=="%s":'%nullvalue,
			'  row.append(None)',
			'else:']+coding.indentList(src, "  ")
	return src


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
}

def getDecoderLines(field):
	"""returns a sequence of python source lines to decode TABLEDATA-encoded
	values for field.
	"""
	if field.a_arraysize not in coding.SINGLEVALUES:
		return _getArrayDecoderLines(field)
	return _decoders[field.a_datatype](field)
