"""
Utilities to write FITS tables
"""

import os
import tempfile
import time
import utils

import numarray
import numarray.strings
import pyfits

import gavo
from gavo import votable


class Error(gavo.Error):
	pass


_naTypesMap = {
	"short": "Int16",
	"int": "Int32",
	"long": "Int64",
	"float": "Float32",
	"double": "Float64",
	"boolean": "Bool",
	"char": "Int8",
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
			return numarray.strings.array(shape=(numItems,))
		else:
			raise Error("Won't represent arrays within numarrays (%s, %s)"%(
				type, arrlen))
	return numarray.array(type=_naTypesMap[type], shape=(numItems,))


def _makeExtension(table):
	"""returns a pyfits hdu for the votable.TableData instance table.
	"""
	colProps = table.getColProperties()
	values = table.get()
	columns = []
	for colInd, cp in enumerate(colProps):
		if cp["datatype"]=="char":
			arr = numarray.strings.array([str(v[colInd]) for v in values])
			typecode = "%dA"%arr.itemsize()
		else:
			arr = numarray.array([v[colInd] for v in values])
			typecode = _fitsCodeMap[cp["datatype"]]
		columns.append(pyfits.Column(name=str(cp["name"]), unit=str(cp["unit"]), 
			format=typecode, null=cp.computeNullvalue(),
			array=arr))
	return pyfits.new_table(pyfits.ColDefs(columns))
	

def makeFITSTable(dataSet):
	"""returns a hdulist containing extensions for the tables in dataSet.
	"""
	tables = [votable.TableData(table) for table in dataSet.getTables()]
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
