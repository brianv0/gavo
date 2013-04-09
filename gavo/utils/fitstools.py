"""
Some utility functions to deal with FITS files.
"""

#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.

# I'm wasting a lot of effort on handling gzipped FITS files, which is
# something that's not terribly common in the end.  Maybe we should
# cut the crap and let people with gzipped FITSes do their stuff manually?


from __future__ import with_statement

import contextlib
import datetime
import gzip
import os
import re
import sys
import tempfile
import warnings

from gavo.utils import excs
from gavo.utils import misctricks
from gavo.utils import ostricks

# Make sure we get the numpy version of pyfits.  This is the master
# import that all others should use (from gavo.utils import pyfits).
# see also utils/__init__.py
os.environ["NUMERIX"] = "numpy"
try:
	import numpy
	import pyfits  # not "from gavo.utils" (this is the original)
except ImportError:  
	# pyfits is not installed; don't die, since the rest of gavo.utils
	# will still work.
	pyfits = misctricks.NotInstalledModuleStub("pyfits and/or numpy")

else:
	# I need some parts of pyfits' internals, and it's version-dependent
	# where they are found
	def _TempHDU(*args):
		raise excs.ReportableError("Incompatible pyfits version."
			"  Please complain to the maintainers.")

	if hasattr(pyfits, "core") and hasattr(pyfits.core, "_TempHDU"):
		_TempHDU = pyfits.core._TempHDU
	elif hasattr(pyfits, "_TempHDU"):
		_TempHDU = pyfits._TempHDU
	elif hasattr(pyfits.Header, "fromstring"):
		class _TempHDU(object):
			"""a wrapper around modern pyfits to provide some ancient whacko
			functionality."""
			def __init__(self):
				self._raw = ""

			def setupHDU(self):
				self.header = pyfits.Header.fromstring(self._raw)
				return self


CARD_SIZE = 80

END_CARD = 'END'+' '*(CARD_SIZE-3)

FITS_BLOCK_SIZE = CARD_SIZE*36


class FITSError(Exception):
	pass


# pyfits is a bit too liberal in throwing depreciation warnings.  Filter them
# for now
warnings.filterwarnings('ignore', category=DeprecationWarning,
	module="gavo.(utils.fitstools|protocols.sdm)")
warnings.filterwarnings('ignore', category=DeprecationWarning,
	module="astLib.*")

def padCard(input, length=CARD_SIZE):
	"""pads input (a string) with blanks until len(result)%80=0

	The length keyword argument lets you adjust the "card size".  Use
	this to pad headers with length=FITS_BLOCK_SIZE

	>>> padCard("")
	''
	>>> len(padCard("end"))
	80
	>>> len(padCard("whacko"*20))
	160
	>>> len(padCard("junkodumnk"*17, 27))%27
	0
	"""
# This is like pyfits._pad, but I'd rather not depend on pyfits internals
# to much.
	l = len(input)
	if not l%length:
		return input
	return input+' '*(length-l%length)


def readHeaderBytes(f, maxHeaderBlocks=40):
	"""returns the bytes beloning to a FITS header starting at the current
	position within the file f.

	If the header is not complete after reading maxHeaderBlocks blocks,
	a FITSError is raised.
	"""
	parts = []

	while True:
		block = f.read(FITS_BLOCK_SIZE)
		if not block:
			raise EOFError('Premature end of file while reading header')

		parts.append(block)
		endCardPos = block.find(END_CARD)
		if not endCardPos%CARD_SIZE:
			break

		if len(parts)>=maxHeaderBlocks:
			raise FITSError("No end card found within %d blocks"%maxHeaderBlocks)
	return "".join(parts)


def readPrimaryHeaderQuick(f, maxHeaderBlocks=40):
	"""returns a pyfits header for the primary hdu of the opened file f.

	This is mostly code lifted from pyfits._File._readHDU.  The way
	that class is made, it's hard to use it with stuff from a gzipped
	source, and that's why this function is here.  It is used in the quick
	mode of fits grammars.

	This function is adapted from pyfits.
	"""
	hdu = _TempHDU()
	hdu._raw = readHeaderBytes(f, maxHeaderBlocks)
	hdu._extver = 1  # We only do PRIMARY

	hdu._new = 0
	hdu = hdu.setupHDU()
	return hdu.header


def parseCards(aString):
	"""returns a list of pyfits Cards parsed from aString.

	This will raise a ValueError if aString's length is not divisible by 80.  
	It may also return pyfits errors for malformed cards.

	Empty (i.e., all-whitespace) cards are ignored.  If an END card is
	encoundered processing is aborted.
	"""
	cards = []
	if len(aString)%CARD_SIZE:
		raise ValueError("parseCards argument has impossible length %s"%(
			len(aString)))
	for offset in range(0, len(aString), CARD_SIZE):
		rawCard = aString[offset:offset+CARD_SIZE]
		if rawCard==END_CARD:
			break
		if not rawCard.strip():
			continue
		cards.append(pyfits.Card().fromstring(rawCard))
	return cards
		

def serializeHeader(hdr):
	"""returns the FITS serialization of a FITS header hdr.
	"""
	parts = []
	for card in hdr.ascardlist():
		r = card.ascardimage('ignore')
		assert not len(r)%CARD_SIZE
		parts.append(r)
	serForm = "".join(parts)+padCard('END')
	return padCard(serForm, length=FITS_BLOCK_SIZE)


def replacePrimaryHeader(inputFile, newHeader, targetFile, bufSize=100000):
	"""writes a FITS to targetFile having newHeader as the primary header,
	where the rest of the data is taken from inputFile.

	inputFile must be a file freshly opened for reading, targetFile one 
	freshly opened for writing.

	This function is (among other things) a workaround for pyfits' misfeature of
	unscaling scaled data in images when extending a header.
	"""
	readPrimaryHeaderQuick(inputFile)
	targetFile.write(serializeHeader(newHeader))
	while True:
		buf = inputFile.read(bufSize)
		if not buf:
			break
		targetFile.write(buf)


def replacePrimaryHeaderInPlace(fitsName, newHeader):
	"""replaces the primary header of fitsName with newHeader.

	Doing this, it tries to minimize the amout of writing necessary; if
	fitsName has enough space for newHeader, just the header is written,
	and newHeader is extended if necessary.  Only if newHeader is longer than
	the existing header is fitsName actually copied.  We try to be safe in
	this case, only overwriting the old entry when the new data is safely
	on disk.

	gzipped inputs used to be supported here, but they aren't any more.
	"""
	if fitsName.endswith(".gz"):
		raise NotImplementedError("replacePrimaryHeaderInPlace no longer"
			" supports gzipped files.")

	serializedNew = serializeHeader(newHeader)
	with open(fitsName) as inputFile:
		serializedOld = readHeaderBytes(inputFile)
		inputFile.seek(0)

		if len(serializedNew)<len(serializedOld):
			# the new header is shorter than the old one; pad it with empty
			# cards, then make sure the end card is in the last block
			serializedNew = serializedNew+(
				len(serializedOld)-len(serializedNew))*" "
			serializedNew = serializedNew.replace(END_CARD, " "*len(END_CARD))
			serializedNew = serializedNew[:-len(END_CARD)]+END_CARD
			assert len(serializedNew)==len(serializedOld)

		if len(serializedNew)==len(serializedOld):
			# header lengths match (after possible padding); just write
			# the new header and be done
			with open(fitsName, "r+") as targetFile:
				targetFile.seek(0)
				targetFile.write(serializedNew)

		else:
			# New header is longer than the old one, write the whole mess.
			with ostricks.safeReplaced(fitsName) as targetFile:
				replacePrimaryHeader(inputFile, newHeader, targetFile)


# enforced sequence of well-known keywords, and whether they are mandatory
keywordSeq = [
	("SIMPLE", True),
	("BITPIX", True),
	("NAXIS", True),
	("NAXIS1", False),
	("NAXIS2", False),
	("NAXIS3", False),
	("NAXIS4", False),
	("EXTEND", False),
	("BZERO", False),
	("BSCALE", False),
]

def _enforceHeaderConstraints(cardList):
	"""returns a pyfits header containing the cards in cardList with FITS
	sequence constraints satisfied.

	This may raise a FITSError if mandatory cards are missing.

	This will only work correctly for image FITSes with less than five 
	dimensions.
	"""
# I can't use pyfits.verify for this since cardList may not refer to
# a data set that's actually in memory
	cardsAdded, newCards = set(), []
	cardDict = dict((card.key, card) for card in cardList)
	for kw, mandatory in keywordSeq:
		try:
			newCards.append(cardDict[kw])
			cardsAdded.add(kw)
		except KeyError:
			if mandatory:
				raise FITSError("Mandatory card '%s' missing"%kw)
	for card in cardList:  # use cardList rather than cardDict to maintain
		                     # cardList order
		if card.key not in cardsAdded:
			newCards.append(card)
	return pyfits.Header(newCards)


def sortHeaders(header, commentFilter=None, historyFilter=None):
	"""returns a pyfits header with "real" cards first, then history, then
	comment cards.

	Blanks in the input are discarded, and one blank each is added in
	between the sections of real cards, history and comments.

	Header can be an iterable yielding Cards or a pyfits header.
	"""
	commentCs, historyCs, realCs = [], [], []
	if hasattr(header, "ascardlist"):
		iterable = header.ascardlist()
	else:
		iterable = header
	for card in iterable:
		if card.key=="COMMENT":
			commentCs.append(card)
		elif card.key=="HISTORY":
			historyCs.append(card)
		elif card.key!="":
			realCs.append(card)

	newCards = []
	for card in realCs:
		newCards.append(card)
	if historyCs:
		newCards.append(pyfits.Card(key=""))
	for card in historyCs:
		if historyFilter is None or historyFilter(card.value):
			newCards.append(card)
	if commentCs:
		newCards.append(pyfits.Card(key=""))
	for card in commentCs:
		if commentFilter is None or commentFilter(card.value):
			newCards.append(card)
	return _enforceHeaderConstraints(newCards)


def openGz(fitsName, tempDir=None):
	"""returns the hdus for the gzipped fits fitsName.

	Scrap that as soon as we have gzipped fits support (i.e. newer pyfits)
	in debian.
	"""
	handle, pathname = tempfile.mkstemp(suffix="fits", dir=tempDir)
	f = os.fdopen(handle, "w")
	f.write(gzip.open(fitsName).read())
	f.close()
	hdus = pyfits.open(pathname)
	hdus.readall()
	os.unlink(pathname) 
	return hdus


def writeGz(hdus, fitsName, compressLevel=5, mode=0664):
	"""writes and gzips hdus into fitsName.  As a side effect, hdus will be 
	closed.

	Appearently, not even recent versions of pyfits support writing of
	zipped files (which is a bit tricky, admittedly).  So, we'll probably
	have to live with this kludge for a while.
	"""
	handle, pathname = tempfile.mkstemp(suffix="fits", 
		dir=base.getConfig("tempDir"))
	with base.silence():
		hdus.writeto(pathname, clobber=True)
	os.close(handle)
	rawFitsData = open(pathname).read()
	os.unlink(pathname)
	handle, pathname = tempfile.mkstemp(suffix="tmp", 
		dir=os.path.dirname(fitsName))
	os.close(handle)
	dest = gzip.open(pathname, "w", compressLevel)
	dest.write(rawFitsData)
	dest.close()
	os.rename(pathname, fitsName)
	os.chmod(fitsName, mode)


def openFits(fitsName):
		"""returns the hdus for fName.

		(gzip detection is tacky, and we should look at the magic).
		"""
		if os.path.splitext(fitsName)[1].lower()==".gz":
			return openGz(fitsName)
		else:
			return pyfits.open(fitsName)


class PlainHeaderManipulator:
	"""A class that allows header manipulation of fits files
	without having to touch the data.

	This class exists because pyfits insists on scaling scaled image data
	on reading it.  While we can scale back on writing, this is something
	I'd rather not do.  So, I have this base class to facilate the 
	HeaderManipulator that can handle gzipped fits files as well.
	"""
	def __init__(self, fName):
		self.hdus = pyfits.open(fName, "update")
		self.add_comment = self.hdus[0].header.add_comment
		self.add_history = self.hdus[0].header.add_history
		self.add_blank = self.hdus[0].header.add_blank
		self.update = self.hdus[0].header.update
	
	def updateFromList(self, kvcList):
		for key, value, comment in kvcList:
			self.hdus[0].header.update(key, value, comment=comment)

	def close(self):
		self.hdus.close()


class GzHeaderManipulator(PlainHeaderManipulator):
	"""is a class that allows header manipulation of fits files without
	having to touch the data even for gzipped files.

	See PlainHeaderManipulator.  We only provide a decoration here that
	transparently gzips and ungzips compressed fits files.
	"""
	def __init__(self, fName, compressLevel=5):
		self.origFile = fName
		handle, self.uncompressedName = tempfile.mkstemp(
			suffix="fits", dir=base.getConfig("tempDir"))
		destFile = os.fdopen(handle, "w")
		destFile.write(gzip.open(fName).read())
		destFile.close()
		self.compressLevel = compressLevel
		PlainHeaderManipulator.__init__(self, self.uncompressedName)
	
	def close(self):
		PlainHeaderManipulator.close(self)
		destFile = gzip.open(self.origFile, "w", compresslevel=self.compressLevel)
		destFile.write(open(self.uncompressedName).read())
		destFile.close()
		os.unlink(self.uncompressedName)


def HeaderManipulator(fName):
	"""returns a header manipulator for a FITS file.

	(it's supposed to look like a class, hence the uppercase name)
	It should automatically handle gzipped files.
	"""
	if fName.lower().endswith(".gz"):
		return GzHeaderManipulator(fName)
	else:
		return PlainHeaderManipulator(fName)


def getPrimarySize(fName):
	"""returns x and y size a fits image.
	"""
	hdr = readPrimaryHeaderQuick(open(fName))
	return hdr["NAXIS1"], hdr["NAXIS2"]


def shrinkWCSHeader(oldHeader, factor):
	"""returns a FITS header suitable for a shrunken version of the image
	described by oldHeader.

	This only works for 2d images, scale must be an integer>1.  The function
	assumes no "fractional" pixels are handled, i.e, remainders in divisions
	with factors are discarded.  It is thus a companion for
	iterScaledRows.

	Note that oldHeader must be an actual pyfits header instance; a dictionary
	will not do.

	This is a pretty straight port of wcstools's imutil.c#ShrinkFITSHeader,
	except we clear BZERO and BSCALE and set BITPIX to -32 (float array)
	under the assumption that in the returned image, 32-bit floats are used.
	"""
	assert oldHeader["NAXIS"]==2

	factor = int(factor)
	newHeader = oldHeader.copy()
	newHeader.update("SIMPLE", True,"GAVO DaCHS, %s"%datetime.datetime.utcnow())
	newHeader["NAXIS1"] = oldHeader["NAXIS1"]//factor
	newHeader["NAXIS2"] = oldHeader["NAXIS2"]//factor
	newHeader["BITPIX"] = -32

	try:
		ffac = float(factor)
		newHeader["CRPIX1"] = oldHeader["CRPIX1"]/ffac+0.5
		newHeader["CRPIX2"] = oldHeader["CRPIX2"]/ffac+0.5
		for key in ("CDELT1", "CDELT2",
				"CD1_1", "CD2_1", "CD1_2", "CD2_2"):
			if key in oldHeader:
				newHeader[key] = oldHeader[key]*ffac
	except KeyError: # no WCS, we're fine either way
		pass

	newHeader.update("IMSHRINK", "Image scaled down %s-fold by DaCHS"%factor)

	for hField in ["BZERO", "BSCALE"]:
		if newHeader.has_key(hField):
			del newHeader[hField]

	return newHeader


NUM_CODE = {
		8: 'uint8', 
		16: '>i2', 
		32: '>i4', 
		64: '>i8', 
		-32: '>f4', 
		-64: '>f8'}

def _makeDecoder(hdr):
	"""returns a decoder for the rows of FITS primary image data.

	The decoder is called with an open file and returns the next row.
	You need to keep track of the total number of rows yourself.
	"""
	numType = NUM_CODE[hdr["BITPIX"]]
	rowLength = hdr["NAXIS1"]

	bzero, bscale = hdr.get("BZERO", 0), hdr.get("BSCALE", 1)
	if bzero!=0 or bscale!=1:
		def read(f):
			return numpy.asarray(
				numpy.fromfile(f, numType, rowLength), 'float32')*bscale+bzero
	else:
		def read(f):
			return numpy.fromfile(f, numType, rowLength)

	return read


def iterFITSRows(hdr, f):
	"""iterates over the rows of a FITS (primary) image.

	You pass in a FITS header and a file positioned to the start of
	the image data.

	What's returned are 1d numpy arrays of the datatype implied by bitpix.  The
	function understands only very basic FITSes (BSCALE and BZERO are known,
	though, and lead to floats arrays).

	We do this ourselves since pyfits may pull in the whole thing or at least
	mmaps it; both are not attractive when I want to stream-process large
	images.
	"""
	decoder = _makeDecoder(hdr)
	for col in xrange(hdr["NAXIS2"]):
		yield decoder(f)


def iterScaledRows(inFile, factor):
	"""iterates over numpy arrays of pixel rows within the open FITS
	stream inFile scaled by it integer in factor.

	The arrays are always float32, regardless of the input.  When the
	image size is not a multiple of factor, border pixels are discarded.

	A FITS header for this data can be obtained using shrinkWCSHeader.
	"""
	factor = int(factor)
	assert factor>1

	inFile.seek(0, 0)
	hdr = readPrimaryHeaderQuick(inFile)
	rowLength = hdr["NAXIS1"]
	destRowLength = rowLength//factor
	rows = iterFITSRows(hdr, inFile)
	summedInds = range(factor)

	for index in xrange(hdr["NAXIS2"]//factor):
		newRow = numpy.zeros((rowLength,), 'float32')
		for i in summedInds:
			try:
				newRow += rows.next()
			except StopIteration:
				break
		newRow /= factor

		# horizontal scaling via reshaping to a matrix and then summing over
		# its columns...
		newRow = newRow[:destRowLength*factor]
		yield sum(numpy.transpose(
			(newRow/factor).reshape((destRowLength, factor))))


def headerFromDict(d):
	"""returns a primary header sporting the key/value pairs given in the
	dictionary d.

	In all likelihood, this header will *not* work properly as a primary
	header because, e.g., there are certain rules on the sequence of
	header items.  fitstricks.copyFields can make a valid header out
	of what's returned here.

	keys mapped to None are skipped, i.e., you have to do nullvalue handling
	yourself.
	"""
	hdr = pyfits.PrimaryHDU().header
	for key, value in d.iteritems():
		if value is not None:
			hdr.update(key, value)
	return hdr


def _test():
	import doctest, fitstools
	doctest.testmod(fitstools)

if __name__=="__main__":
	_test()
