"""
Helpers for manipulating FITS files.

In contrast to fitstools, this is not for online processing or import of
files, but just for the manipulation before processing.

Rough guideline: if it's about writing fixed fits files, it probably belongs
here, otherwise it goes to fitstools.

Realistically, this module has been hemorraghing functions to
fitstools and probably should be removed completely.
"""

from gavo.utils import fitstools
from gavo.utils import pyfits

from gavo.utils.fitstools import replacePrimaryHeader

def copyFields(header, cardList, ignoredHeaders):
	"""copies over all cards from cardList into header, excluding headers
	named in ignoredHeaders.

	ignoredHeaders must be all lowercase.
	"""
	for card in cardList:
		if card.key=="COMMENT":
			header.add_comment(card.value)
		elif card.key=="HISTORY":
			header.add_history(card.value)
		elif card.key=="":
			header.add_blank(card.value, card.comment)
		elif card.key.lower() in ignoredHeaders:
			pass
		else:
			header.update(card.key, card.value, card.comment)
