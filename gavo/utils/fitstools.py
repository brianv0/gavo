"""
Some utility functions to deal with fits files.
"""

import tempfile
import os
import sys
import gzip
import re


from gavo.utils import ostricks

# Make sure we get the numpy version of pyfits.  This is the master
# import that all others should use (from gavo.utils import pyfits).
# see also utils/__init__.py
os.environ["NUMERIX"] = "numpy"
import pyfits  # not from gavo.utils to avoid circular import


blockLen = 2880

if hasattr(pyfits, "core"):
	_TempHDU = pyfits.core._TempHDU
	_pad = pyfits.core._pad
	_padLength = pyfits.core._padLength
else:
	_TempHDU = pyfits._TempHDU
	_pad = pyfits._pad
	_padLength = pyfits._padLength


def readPrimaryHeaderQuick(f):
	"""returns a pyfits header for the primary hdu of the opened file f.

	This is mostly code lifted from pyfits._File._readHDU.  The way
	that class is made, it's hard to use it with stuff from a gzipped
	source, and that's why this function is here.  It is used in the quick
	mode of fits grammars.
	"""
	end_RE = re.compile('END'+' '*77)
	block = f.read(blockLen)
	if block == '':
		raise EOFError

	hdu = _TempHDU()
	hdu._raw = ''

	# continue reading header blocks until END card is reached
	while 1:
		mo = end_RE.search(block)
		if mo is None:
			hdu._raw += block
			block = f.read(blockLen)
			if block == '' or len(hdu._raw)>40000:
				break
		else:
			break
	hdu._raw += block

	_size, hdu.name = hdu._getsize(hdu._raw)

	hdu._extver = 1  # We only do PRIMARY

	hdu._new = 0
	hdu = hdu.setupHDU()
	return hdu.header


def hdr2str(hdr):
	repr = "".join(map(str, hdr.ascardlist()))
	repr = repr+_pad('END')
	repr = repr+_padLength(len(repr))*' '
	return repr


def replacePrimaryHeader(inputFile, newHeader, targetFile, bufSize=100000):
	"""writes a FITS to targetFile having newHeader as the primary header,
	where the rest of the data is taken from inputFile.

	inputFile must be a file freshly opened for reading, targetFile one 
	freshly opened for writing.

	This function is a workaround for pyfits' misfeature of unscaling
	scaled data in images when extending a header.
	"""
	readPrimaryHeaderQuick(inputFile)
	targetFile.write(hdr2str(newHeader))
	while True:
		buf = inputFile.read(bufSize)
		if not buf:
			break
		targetFile.write(buf)


def _enforceHeaderConstraints(cardList):
	"""changes the order of cardList in place in order to satisfy some
	FITS constraints.
	"""
# I can't use pyfits.verify for this since cardList may not refer to
# a data set that's actually in memory

	def moveExtend(cardList):
		# make sure extend is right after the last NAXIS.* card
		extendPos = None
		lastNaxis = -1
		for pos, card in enumerate(cardList):
			if card.key.startswith("NAXIS"):
				lastNaxis = pos
			if card.key=='EXTEND':
				extendPos = pos
		if not extendPos or extendPos-1==lastNaxis:
			return
		extCard = cardList[extendPos]
		del cardList[extendPos]
		if extendPos<lastNaxis:
			lastNaxis = lastNaxis-1
		cardList.insert(lastNaxis+1, extCard)
	
	moveExtend(cardList)


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
		if not historyFilter or historyFilter(card.value):
			newCards.append(card)
	if commentCs:
		newCards.append(pyfits.Card(key=""))
	for card in commentCs:
		if not commentFilter or commentFilter(card.value):
			newCards.append(card)
	_enforceHeaderConstraints(newCards)
	return pyfits.Header(newCards)


def replacePrimaryHeaderInPlace(fitsName, newHeader):
	"""is a convenience wrapper around replacePrimaryHeader.
	"""
	targetDir = os.path.abspath(os.path.dirname(fitsName))
	oldMode = os.stat(fitsName)[0]
	handle, tempName = tempfile.mkstemp(".temp", "", targetDir)
	try:
		targetFile = os.fdopen(handle, "w")
		inputFile = open(fitsName)
		replacePrimaryHeader(inputFile, newHeader, targetFile)
		inputFile.close()
		ostricks.safeclose(targetFile)
		os.rename(tempName, fitsName)
		os.chmod(fitsName, oldMode)
	finally:
		try:
			os.unlink(tempName)
		except os.error:
			pass


def openGz(fitsName):
	"""returns the hdus for the gzipped fits fitsName.

	Scrap that as soon as we have gzipped fits support (i.e. newer pyfits)
	in debian.
	"""
	handle, pathname = tempfile.mkstemp(suffix="fits", dir=base.getConfig("tempDir"))
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
	handle, pathname = tempfile.mkstemp(suffix="fits", dir=base.getConfig("tempDir"))
	base.silence(hdus.writeto, pathname, clobber=True)
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
	"""is a class that allows header manipulation of fits files
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
	"""is a factory function for header manipulators.

	(it's supposed to look like a class, hence the uppercase name)
	It should automatically handle gzipped files.
	"""
	if fName.lower().endswith(".gz"):
		return GzHeaderManipulator(fName)
	else:
		return PlainHeaderManipulator(fName)
