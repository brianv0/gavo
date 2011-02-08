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
_formatsMIMERegistry = {}


class CannotSerializeIn(base.Error):
	def __init__(self, format):
		self.format = format
		base.Error.__init__(self, format,
			hint="Either you gave an invalid format id or a known format"
			" did not get registred for some reason.  Format codes"
			" known at this point: %s."%", ".join(_formatDataRegistry))
		self.args = [format]
	
	def __str__(self):
		return "Cannot serialize in '%s'."%self.format


def registerDataWriter(key, writer, mime):
	_formatDataRegistry[key] = writer
	_formatsMIMERegistry[key] = mime


def getMIMEFor(formatName):
	"""returns a MIME type for our internal formatName.

	This will return application/octet-stream for unknown formats.
	"""
	return _formatsMIMERegistry.get(formatName, "application/octet-stream")


def checkFormatIsValid(formatName):
	"""raises a CannotSerializeIn exception if formatData would fail with one.
	"""
	if formatName not in _formatDataRegistry:
		raise CannotSerializeIn(formatName)


def formatData(key, table, outputFile, acquireSamples=True):
	"""writes a table to outputFile in the format given by key.

	key points into the _formatDataRegistry.  Table may be a table or a
	Data instance.
	"""
	checkFormatIsValid(key)
	_formatDataRegistry[key](table, outputFile, acquireSamples=acquireSamples)
