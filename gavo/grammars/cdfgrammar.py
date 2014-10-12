"""
A grammar wrapping spacepy to parse files in the Common Data Format (CDF),
http://cdf.gsfc.nasa.gov.
"""

from gavo import base
from gavo.grammars.common import Grammar, RowIterator, MapKeys


class CDFHeaderIterator(RowIterator):
	"""an iterator for headers of CDF files.
	"""
	def _iterRows(self):
		try:
			from spacepy import pycdf
		except ImportError:
			raise base.ReportableError("cdfHeaderGrammar needs the external"
				" spacepy package.  You can obtain it from"
				" http://spacepy.lanl.gov.")
		
		cdfStruct = pycdf.CDF(self.sourceToken)
		# we return a copy so libcdf doesn't try to write anything back
		yield cdfStruct.attrs.copy()


class CDFHeaderGrammar(Grammar):
	"""A grammar that returns the header dictionary of a CDF file
	(global attributes).

	This grammar yields a single dictionary per file, which corresponds
	to the global attributes.  The values in this dictionary may have
	complex structure; in particular, sequences are returned as lists.

	To use this grammar, additional software is required that (by 2014)
	is not packaged for Debian.  See
	http://spacepy.lanl.gov/doc/install_linux.html for installation 
	instructions.  Note that you must install the CDF library itself as
	described further down on that page; the default installation 
	instructions do not install the library in a public place, so if
	you use these, you'll have to set CDF_LIB to the right value, too.
	"""
	name_ = "cdfHeaderGrammar"

	_mapKeys = base.StructAttribute("mapKeys", childFactory=MapKeys,
		default=None, copyable=True, description="Prescription for how to"
		" map labels keys to grammar dictionary keys")

	rowIterator = CDFHeaderIterator

	def onElementComplete(self):
		if self.mapKeys is None:
			self.mapKeys = base.makeStruct(MapKeys)
		self._onElementCompleteNext(CDFHeaderGrammar)
