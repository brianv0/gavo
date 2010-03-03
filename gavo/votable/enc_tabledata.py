"""
Coding and decoding from tabledata.
"""

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


_decoders = {
	'boolean': [
		'row.append(TDENCBOOL[val.strip().lower()])'],
	'bit': [
		'row.append(int(val))'],
	'unsignedByte': _makeByteDecoder,
}

def getDecoderLines(field):
	"""returns a sequence of python source lines to decode TABLEDATA-encoded
	values for field.
	"""
	if field.a_arraysize not in coding.SINGLEVALUES:
		return _getArrayDecoderLines(field)
	dec = _decoders[field.a_datatype]
	# dec may either be a list of a function to compute that list
	if isinstance(dec, list):
		return dec
	return dec(field)
