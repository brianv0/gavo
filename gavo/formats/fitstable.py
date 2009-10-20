"""
Utilities to write FITS tables
"""

import os
import tempfile
import time

import numpy

from gavo import base
from gavo import utils
from gavo.utils import pyfits


_naTypesMap = {
	"short": numpy.int16,
	"int": numpy.int32,
	"long": numpy.int64,
	"float": numpy.float32,
	"double": numpy.float64,
	"boolean": numpy.bool,
	"char": numpy.str,
}

_fitsCodeMap = {
	"short": "I",
	"int": "J",
	"long": "K",
	"float": "E",
	"double": "D",
	"boolean": "L",
	"char": "A",
}

def makeArrayForVOType(type, arrsz, numItems):
# not needed for now
	if arrsz!="1":
		if type=="char":
			return numpy.array(shape=(numItems,), dtype=numpy.str)
		else:
			raise utils.Error("Won't represent arrays within numpy arrays (%s, %s)"%(
				type, arrlen))
	return numpy.array(dtype=_naTypesMap[type], shape=(numItems,))


def _makeExtension(serMan):
	"""returns a pyfits hdu for the valuemappers.SerManager instance table.
	"""
	values = list(serMan.getMappedTuples())
	columns = []
	for colInd, colDesc in enumerate(serMan):
		if colDesc["datatype"]=="char":
			arr = numpy.array([str(v[colInd]) for v in values], dtype=numpy.str)
			typecode = "%dA"%arr.itemsize
		else:
			arr = numpy.array([v[colInd] for v in values])
			typecode = _fitsCodeMap[colDesc["datatype"]]
		columns.append(pyfits.Column(name=str(colDesc["name"]), 
			unit=str(colDesc["unit"]), format=typecode, 
			null=colDesc.computeNullvalue(), array=arr))
	return pyfits.new_table(pyfits.ColDefs(columns))
	

def makeFITSTable(dataSet):
	"""returns a hdulist containing extensions for the tables in dataSet.
	"""
	tables = [base.SerManager(table) for table in dataSet.tables.values()]
	extensions = [_makeExtension(table) for table in tables]
	primary = pyfits.PrimaryHDU()
	primary.header.update("DATE", time.strftime("%Y-%m-%d"), 
		"Date file was written")
	return pyfits.HDUList([primary]+extensions)


def makeFITSTableFile(dataSet):
	"""returns the name of a temporary file containing a fits file
	representing dataSet.

	The caller is responsible to remove the file.
	"""
	hdulist = makeFITSTable(dataSet)
	handle, pathname = tempfile.mkstemp(".fits")
	utils.silence(hdulist.writeto, pathname, clobber=1)
	os.close(handle)
	return pathname
