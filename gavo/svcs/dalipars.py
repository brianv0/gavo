"""
DALI-type input parameters.

These, in particular, make intervals out of floats;  uploads are as in "PQL".

All this is rife with crazy rules and conventions.  I'd much rather
we hadn't gone for intervals, but... well, the standards process went the
other way.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.



INTERVAL_TYPES = set(
	["real", "double precision", "timestamp", "date", "bigint", 
		"integer", "smallint"])


def adaptInputKey(inputKey):
	"""returns inputKey changed to generate SQL for DALI-standard parameters.

	This is used by buildFrom on CondDescs when renderers have a 
	parameterStyle of dali.

	It will return intervals for INTERVAL_TYPES, make enumerated keys
	multiple, turn dates and timestamps into MJD intervals.

	InputKeys that already have xtypes are returned unchanged.
	"""
	if inputKey.xtype:
		return inputKey

	if inputKey.type in ["timestamp", "date"]:
		res = inputKey.change(unit="d", xtype="interval",
			type="double precision[2]", multiplicity="single")
		res.setProperty("database-column-is-date", "")
		return res

	if inputKey.type in INTERVAL_TYPES:
		if not inputKey.isEnumerated():
			return inputKey.change(type=inputKey.type+"[2]", xtype="interval",
				multiplicity="single")
	
	return inputKey
