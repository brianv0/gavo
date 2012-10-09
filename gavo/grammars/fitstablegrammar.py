"""
A grammar taking rows from a FITS table.
"""

from gavo import base
from gavo.grammars import common

from gavo.utils import pyfits

class FITSTableIterator(common.RowIterator):
	"""The row iterator for FITSTableGrammars.
	"""
	def _iterRows(self):
		hdus = pyfits.open(self.sourceToken)
		fitsTable = hdus[self.grammar.hdu].data
		names = [n for n in fitsTable.dtype.names]
		for row in fitsTable:
			yield dict(zip(names, row))


class FITSTableGrammar(common.Grammar):
	"""A grammar parsing from FITS tables.

	fitsTableGrammar result in typed records, i.e., values normally come
	in the types they are supposed to have.  Of course, that won't work
	for datetimes, STC-S regions, and the like.

	The keys of the result dictionaries are simpily the names given in
	the FITS.
	"""
	name_ = "fitsTableGrammar"

	_hduIndex = base.IntAttribute("hdu", default=1,
		description="Take the data from this extension (primary=0)."
			" Tabular data typically resides in the first extension.")

	rowIterator = FITSTableIterator
