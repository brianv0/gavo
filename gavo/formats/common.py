"""
Common code for generation of various data formats.

The main function here is formatData.  It receives a string format id,
a data instance and a destination file.  It dispatches this to formatters 
previously registred using registerDataWriter.

The data writers must take a data instance and a file instance; their
effect must be that a serialized representation of data, or, if the format
does not support this, the data's primary table is written to the file 
instance.
"""

from gavo import base

_formatDataRegistry = {}


class CannotSerializeIn(base.Error):
	def __init__(self, format):
		self.format = format
		base.Error.__init__(self, "Cannot serialize in %s."%self.format,
			hint="Either you gave an invalid format id or the a known format"
			" did not get registred for some reason.  Format codes"
			" known at this point: %s."%", ".join(_formatDataRegistry))


def registerDataWriter(key, writer):
	_formatDataRegistry[key] = writer


def formatData(key, table, outputFile):
	"""writes a table to outputFile in the format given by key.

	key points into the _formatDataRegistry.  Table my be a table or a
	Data instance.
	"""
	if key not in _formatDataRegistry:
		raise CannotSerializeIn(key)
	_formatDataRegistry[key](table, outputFile)
