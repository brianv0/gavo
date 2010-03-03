"""
Coding and decoding from tabledata.
"""

import re

from gavo.votable import coding


def _makeByteDecoder(field):
	src = [
		'if not val:',
		'  row.append(None)',
		'elif val.startswith("0x"):',
		'  row.append(int(val[2:], 16))',
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
# Note that Elementtree already made sure we're only seeing unicode strings
# here.
	return [
		'if not val:',
		'  val = None',
		'else:',
		'  if "&" in val:',
		'    val = utils.remplaceXMLEntityRefs(val)',
		'row.append(val)']


def _makeBooleanDecoder(field):
	return ['row.append(TDENCBOOL[val.strip().lower()])']


def _makeBitDecoder(field):
	return ['row.append(int(val))']


_decoders = {
	'boolean': _makeBooleanDecoder,
	'bit': _makeBitDecoder,
	'unsignedByte': _makeByteDecoder,
	'char': _makeCharDecoder,
}

def getDecoderLines(field):
	"""returns a sequence of python source lines to decode TABLEDATA-encoded
	values for field.
	"""
	if field.a_arraysize not in coding.SINGLEVALUES:
		return _getArrayDecoderLines(field)
	return _decoders[field.a_datatype](field)
