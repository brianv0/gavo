"""
Writing data in FITS binary tables
"""

import os
import tempfile
import time

import numpy

from gavo import base
from gavo import rsc
from gavo import utils
from gavo.formats import common
from gavo.utils import pyfits


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


def writeDataAsFITS(data, outputFile):
	"""a formats.common compliant data writer.
	"""
	data = rsc.wrapTable(data)
	fitsName = makeFITSTableFile(data)
	try:
		src = open(fitsName)
		utils.cat(src, outputFile)
		src.close()
	finally:
		os.unlink(fitsName)

common.registerDataWriter("fits", writeDataAsFITS, "application/fits")
