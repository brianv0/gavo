"""
This module contains code for using fits files as source files (probably
mostly for rows).
"""

import re
import pyfits
import gzip

from gavo import record
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
			"qnd": record.BooleanField,
		})
		self.set_docIsRow(True)
	
	def parse(self, parseContext):
		"""opens the fits file and calls the document handler with the header
		dict.

		Unfortunately, pyfits insists on getting a file name as opposed to
		an open file as provided by parseContext.  We fix this by assuming
		that parseContext really talks about a disk file and contains a
		valid file name.
		"""
		parseContext.sourceFile.close()
		if self.get_qnd():
			self._parseFast(parseContext)
		else:
			self._parseSlow(parseContext)

	def _hackBotchedCard(self, card, res):
		"""tries to make *anything* from a card pyfits doesn't want to parse.

		In reality, I'm just trying to cope with oversized keywords.
		"""
		mat = re.match(r"([^\s=]*)\s*=\s*([^/]+)", card._cardimage)
		res[mat.group(1)] = mat.group(2).strip()

	def _buildDictFromHeader(self, header):
		res = {}
		for card in header.ascard:
			try:
				res[card.key] = card.value
			except ValueError:
				self._hackBotchedCard(card, res)
		return res

	def _parseFast(self, parseContext):
		fName = parseContext.sourceName
		if fName.endswith(".gz"):
			f = gzip.open(fName)
		else:
			f = open(fName)
		header = fitstools.readPrimaryHeaderQuick(f)
		f.close()
		self.handleDocdict(self._buildDictFromHeader(header), parseContext)

	def _parseSlow(self, parseContext):
		hdus = fitstools.openFits(parseContext.sourceName)
		header = hdus[int(self.get_hduIndex())].header
		hdus.close()
		self.handleDocdict(self._buildDictFromHeader(header), parseContext)
	
	def enableDebug(self, debugProductions):
		pass
