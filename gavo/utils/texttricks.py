"""
Formatting and text manipulation code independent of GAVO code.
"""

def formatSize(val, sf=1):
	"""returns a human-friendly representation of a file size.
	"""
	if val<1e3:
		return "%d Bytes"%int(val)
	elif val<1e6:
		return "%.*fkiB"%(sf, val/1024.)
	elif val<1e9:
		return "%.*fMiB"%(sf, val/1024./1024.)
	else:
		return "%.*fGiB"%(sf, val/1024./1024./1024)
