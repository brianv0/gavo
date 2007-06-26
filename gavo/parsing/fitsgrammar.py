"""
This module contains code for using fits files as source files (probably
mostly for rows).
"""

import re
import pyfits
import gzip

from gavo import utils
from gavo import fitstools
from gavo.parsing import grammar


class FitsGrammar(grammar.Grammar):
	"""models a "grammar" that just returns the head of a FITS file
	as a dictionary.

	By default, the first HDU is examined.

	Row dictionaries -- the communication means between grammars and semantics
	-- cannot store more than one header field, whereas fits files may
	have as many values to a header as they like.  This *may* become
	a problem at some point.  Right now, the value in the row dictionary 
	is whatever pyfits returns for that key.

	You can set the qnd ("Quick and dirty") mode if all you're interested
	in is the primary header.  This helps when your files are gzipped, because
	the fitstool support uncompresses the entire file when you really only
	need the first couple of kB.
	"""
	def __init__(self):
		grammar.Grammar.__init__(self, {
			"hduIndex": 0,
			"qnd": utils.BooleanField,
		})
	
	def _parse(self, inputFile):
		"""opens the fits file and calls the document handler with the header
		dict.

		It's a major pain that we want an open file as an argument, since pyfits
		insists on opening the files on disk.  We have to rely on the fact
		that inputFile really correspondes to a file on disk and use Grammar's
		getCurFileName method after closing inputFile.
		"""
		inputFile.close()
		if self.get_qnd():
			self._parseFast()
		else:
			self._parseSlow()

	def _parseFast(self):
		fName = self.getCurFileName()
		if fName.endswith(".gz"):
			f = gzip.open(fName)
		else:
			f = open(fName)
		header = fitstools.readPrimaryHeaderQuick(f)
		f.close()
		self.handleDocument(dict([(key, header[key]) 
			for key in header.ascardlist().keys()]))

	def _parseSlow(self):
		hdus = fitstools.openFits(self.getCurFileName())
		header = hdus[int(self.get_hduIndex())].header
		self.handleDocument(dict([(key, header[key]) 
			for key in header.ascardlist().keys()]))
		hdus.close()
	
	def setRowHandler(self, callable):
		if callable:
			raise gavo.Error("FitsGrammars can have no row handlers")
	
	def enableDebug(self, debugProductions):
		pass
