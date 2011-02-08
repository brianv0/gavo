"""
Writing data in FITS binary tables
"""

from __future__ import with_statement

import mutex
import os
import tempfile
import time
from contextlib import contextmanager

import numpy

from gavo import base
from gavo import rsc
from gavo import utils
from gavo.formats import common
from gavo.utils import pyfits


# pyfits obviously is not thread-safe.  We put a mutex around table generation
# and hope we'll be fine.
_FITS_TABLE_MUTEX = mutex.mutex()

@contextmanager
def exclusiveFits():
	while not _FITS_TABLE_MUTEX.testandset():
		time.sleep(0.1)
	yield
	_FITS_TABLE_MUTEX.unlock()



_fitsCodeMap = {
	"short": "I",
	"int": "J",
	"long": "K",
	"float": "E",
	"double": "D",
	"boolean": "L",
	"char": "A",
}


def _makeExtension(serMan):
	"""returns a pyfits hdu for the valuemappers.SerManager instance table.
	"""
	values = list(serMan.getMappedTuples())
	columns = []
	for colInd, colDesc in enumerate(serMan):
		if colDesc["datatype"]=="char":
			try:
				arr = numpy.array([str(v[colInd]) for v in values], dtype=numpy.str)
			except UnicodeEncodeError:
				arr = numpy.array([str(v[colInd].encode("utf-8")) for v in values], 
					dtype=numpy.str)
			typecode = "%dA"%arr.itemsize
		else:
			arr = numpy.array([v[colInd] for v in values])
			typecode = _fitsCodeMap[colDesc["datatype"]]
		columns.append(pyfits.Column(name=str(colDesc["name"]), 
			unit=str(colDesc["unit"]), format=typecode, 
			null=colDesc.computeNullvalue(), array=arr))
	return pyfits.new_table(pyfits.ColDefs(columns))
	

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


def makeFITSTable(dataSet, acquireSamples=True):
	"""returns a hdulist containing extensions for the tables in dataSet.

	This function may block basically forever.  Never call this from
	the main server, always use threads or separate processes (until
	pyfits is fixed to be thread-safe).
	"""
	with exclusiveFits():
		return _makeFITSTableNOLOCK(dataSet, acquireSamples)


def makeFITSTableFile(dataSet, acquireSamples=True):
	"""returns the name of a temporary file containing a fits file
	representing dataSet.

	The caller is responsible to remove the file.
	"""
	hdulist = makeFITSTable(dataSet, acquireSamples)
	handle, pathname = tempfile.mkstemp(".fits", dir=base.getConfig("tempDir"))
	with utils.silence():
		hdulist.writeto(pathname, clobber=1)
	os.close(handle)
	return pathname


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
