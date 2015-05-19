"""
Serialisation of python values to VOTable PARAM values.

This has two aspects:

* Guessing proper VOTable type descriptors for python values
* Serialising the python values to strings suitable for the PARAM.
"""

import datetime

from gavo import utils
from gavo.utils import pgsphere


_SEQUENCE_TYPES = (tuple, list)
_ATOMIC_TYPES = [
	(long, {"datatype": "long"}),
	(int, {"datatype": "int"}),
	(str, {"datatype": "char", "arraysize": "*"}),
	(float, {"datatype": "double"}),
	(type(None), {"datatype": "double"}),
	(complex, {"datatype": "doubleComplex"}),
	(datetime.datetime, {"datatype": "char", 
		"arraysize": "20",
		"xtype": "adql:TIMESTAMP"}),
	(pgsphere.SPoint, {"datatype": "char", 
		"arraysize": "*",
		"xtype": "adql:POINT"}),]


def _combineArraysize(arraysize, attrs):
	"""makes an arraysize attribute for a value with attrs.

	This will in particular check that any existing arraysize in
	attrs does not end with a star (as variable length is only allowed
	in the slowest coordinate).

	attrs is changed in place.
	"""
	if "arraysize" in attrs:
		if attrs["arraysize"].endswith("*"):
			raise ValueError("Arrays of variable-length arrays are not allowed.")
		attrs["arraysize"] = "%sx%s"%(attrs["arraysize"], arraysize)
	else:
		attrs["arraysize"] = arraysize
	

def _guessParamAttrsForSequence(pythonVal):
	"""helps guessParamAttrsForValue when the value is a sequence.
	"""
	arraysize = str(len(pythonVal))
	if len(pythonVal)==0:
		return {
			"datatype": "char",
			"arraysize": "0"}

	elementVal = pythonVal[0]

	if isinstance(elementVal, basestring):
		# special case as this may become common
		attrs = {
			"arraysize": "%sx%s"%(
				max(len(s) for s in pythonVal), arraysize),
			"datatype": "char"}
	
	elif isinstance(elementVal, _SEQUENCE_TYPES):
		attrs = _guessParamAttrsForSequence(elementVal)
		_combineArraysize(arraysize, attrs)
	
	else:
		attrs = _guessParamAttrsForAtom(elementVal)
		_combineArraysize(arraysize, attrs)

	return attrs


def _guessParamAttrsForAtom(pythonVal):
	"""helps guessParamAttrsForValue when the value is atomic.

	(where "atomic" includes string, and other things that actually
	have non-1 arraysize).
	"""
	for type, attrs in _ATOMIC_TYPES:
		if isinstance(pythonVal, type):
			return attrs.copy()

	raise utils.NotFoundError(repr(pythonVal),
		"VOTable type code for", "paramval.py predefined types")


def guessParamAttrsForValue(pythonVal):
	"""returns a dict of proposed attributes for a PARAM to keep pythonVal.

	There is, of course, quite a bit of heuristics involved.  For instance,
	we assume sequences are homogeneous.
	"""
	if isinstance(pythonVal, _SEQUENCE_TYPES):
		return _guessParamAttrsForSequence(pythonVal)

	else:
		return _guessParamAttrsForAtom(pythonVal)
