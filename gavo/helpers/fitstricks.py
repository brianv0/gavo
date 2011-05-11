"""
Helpers for manipulating FITS files.

In contrast to fitstools, this is not for online processing or import of
files, but just for the manipulation before processing.

Rough guideline: if it's about writing fixed fits files, it probably belongs
here, otherwise it goes to fitstools.
"""

from gavo.utils import fitstools
from gavo.utils import pyfits


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


def hdr2str(hdr):
	"""returns the FITS serialization of a FITS header hdr.
	"""
	repr = "".join(map(str, hdr.ascardlist()))
	repr = repr+pyfits._pad('END')
	repr = repr+pyfits._padLength(len(repr))*' '
	return repr


def replacePrimaryHeader(inputFile, newHeader, targetFile, bufSize=100000):
	"""writes a FITS to targetFile having newHeader as the primary header,
	where the rest of the data is taken from inputFile.

	inputFile must be a file freshly opened for reading, targetFile one 
	freshly opened for writing.

	This function is a workaround for pyfits' misfeature of unscaling
	scaled data in images when extending a header.
	"""
	fitstools.readPrimaryHeaderQuick(inputFile)
	targetFile.write(hdr2str(newHeader))
	while True:
		buf = inputFile.read(bufSize)
		if not buf:
			break
		targetFile.write(buf)


def shrinkWCSHeader(oldHeader, factor):
	"""returns a FITS header suitable for a shrunken version of the image
	described by origHeader.

	This only works for 2d images, and you're doing yourself a favour
	if factor is a power of 2.  It is forced to be integral anyway.

	This is a pretty straight port of wcstools's imutil.c#ShrinkFITSHeader
	"""
	assert oldHeader["NAXIS"]==2

	factor = int(factor)
	newHeader = oldHeader.copy()
	newHeader["NAXIS1"] = oldHeader["NAXIS1"]//factor
	newHeader["NAXIS2"] = oldHeader["NAXIS2"]//factor

	ffac = float(factor)
	newHeader["CRPIX1"] = oldHeader["CRPIX1"]/ffac+0.5
	newHeader["CRPIX2"] = oldHeader["CRPIX2"]/ffac+0.5
	for key in ("CDELT1", "CDELT2",
			"CD1_1", "CD2_1", "CD1_2", "CD2_2"):
		newHeader[key] = oldHeader[key]*ffac
	newHeader["IMSHRINK"] = "Image scaled by %s"%factor

	return newHeader
