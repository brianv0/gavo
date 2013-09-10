"""
Writing data in FITS binary tables
"""

from __future__ import with_statement

import os
import tempfile
import threading
import time
from contextlib import contextmanager

import numpy

from gavo import base
from gavo import rsc
from gavo import utils
from gavo.formats import common
from gavo.utils import pyfits


# pyfits obviously is not thread-safe.  We put a lock around table generation
# and hope we'll be fine.
_FITS_TABLE_LOCK = threading.Lock()

@contextmanager
def exclusiveFits():
	_FITS_TABLE_LOCK.acquire()
	try:
		yield
	finally:
		_FITS_TABLE_LOCK.release()



_fitsCodeMap = {
	"short": "I",
	"int": "J",
	"long": "K",
	"float": "E",
	"double": "D",
	"boolean": "L",
	"char": "A",
}


def _makeStringArray(values, colInd, colDesc):
	"""returns a pyfits-capable column array for strings stored in the colInd-th
	column of values.
	"""
	try:
		arr = numpy.array([str(v[colInd]) for v in values], dtype=numpy.str)
	except UnicodeEncodeError:
		arr = numpy.array([str(v[colInd].encode("utf-8")) for v in values], 
			dtype=numpy.str)
	return "%dA"%arr.itemsize, arr


def _makeValueArray(values, colInd, colDesc):
	"""returns a pyfits-capable column array for non-string values
	stored in the colInd-th column of values.
	"""
	nullValue = colDesc["nullvalue"]
	if nullValue is None:
		# enter some reasonable defaults
		if (colDesc["datatype"]=="float"
			or colDesc["datatype"]=="double"):
			nullValue = float("NaN")
		elif colDesc["datatype"]=="text":
			nullValue = ""

	def mkval(v):
		if v is None:
			if nullValue is None:
				raise ValueError("While serializing a FITS table: NULL"
					" detected in column '%s' but no null value declared"%
					colDesc["name"])
			return nullValue
		else:
			return v

	arr = numpy.array([mkval(v[colInd]) for v in values])
	typecode = _fitsCodeMap[colDesc["datatype"]]
	return typecode, arr


def _makeExtension(serMan):
	"""returns a pyfits hdu for the valuemappers.SerManager instance table.
	"""
	values = list(serMan.getMappedTuples())
	columns = []
	utypes = []

	for colInd, colDesc in enumerate(serMan):
		if colDesc["datatype"]=="char":
			makeArray = _makeStringArray
		else:
			makeArray = _makeValueArray
		typecode, arr = makeArray(values, colInd, colDesc)
		columns.append(pyfits.Column(name=str(colDesc["name"]), 
			unit=str(colDesc["unit"]), format=typecode, 
			null=colDesc.nullvalueInType(), array=arr))
		if colDesc["utype"]:
			utypes.append((colInd, str(colDesc["utype"].lower())))

	hdu = pyfits.new_table(pyfits.ColDefs(columns))
	for colInd, utype in utypes:
		hdu.header.update("TUTYP%d"%(colInd+1), utype)
	return hdu
	

def _makeFITSTableNOLOCK(dataSet, acquireSamples=True):
	"""returns a hdulist containing extensions for the tables in dataSet.

	You must make sure that this function is only executed once
	since pyfits is not thread-safe.
	"""
	tables = [base.SerManager(table, acquireSamples=acquireSamples) 
		for table in dataSet.tables.values()]
	extensions = [_makeExtension(table) for table in tables]
	primary = pyfits.PrimaryHDU()
	primary.header.update("DATE", time.strftime("%Y-%m-%d"), 
		"Date file was written")
	return pyfits.HDUList([primary]+extensions)


def makeFITSTable(dataSet, acquireSamples=False):
	"""returns a hdulist containing extensions for the tables in dataSet.

	This function may block basically forever.  Never call this from
	the main server, always use threads or separate processes (until
	pyfits is fixed to be thread-safe).
	"""
	with exclusiveFits():
		return _makeFITSTableNOLOCK(dataSet, acquireSamples)


def writeFITSTableFile(hdulist):
	"""returns the name of a temporary file containing the FITS data for
	hdulist.
	"""
	handle, pathname = tempfile.mkstemp(".fits", dir=base.getConfig("tempDir"))
	with utils.silence():
		hdulist.writeto(pathname, clobber=1)
	os.close(handle)
	return pathname


def makeFITSTableFile(dataSet, acquireSamples=True):
	"""returns the name of a temporary file containing a fits file
	representing dataSet.

	The caller is responsible to remove the file.
	"""
	hdulist = makeFITSTable(dataSet, acquireSamples)
	return writeFITSTableFile(hdulist)


def writeDataAsFITS(data, outputFile, acquireSamples=False):
	"""a formats.common compliant data writer.
	"""
	data = rsc.wrapTable(data)
	fitsName = makeFITSTableFile(data, acquireSamples)
	try:
		src = open(fitsName)
		utils.cat(src, outputFile)
		src.close()
	finally:
		os.unlink(fitsName)

common.registerDataWriter("fits", writeDataAsFITS, "application/fits")
