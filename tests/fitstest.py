"""
Tests for fits helpers
"""

import cStringIO
import os
import shutil
import tempfile
import unittest

from gavo.helpers import testhelpers

from gavo import base
from gavo.utils import fitstools
from gavo.utils import pyfits


_fitsData = \
"""eJzt0b0KwjAUhmH/f+7i3IFWZwfFCgEthXboGm0LHZpIUofevaeIuCRIwUm+B76teTnQRFzic0i0
I4eUVnTTqtSmttRoOok0IdtIlUuTux4QHUQai8zd2264J42RLeWykdS098Jd+Yj2mUjIc1/XU4/6
WhjS5btc1YWylVbW3wvcvWD97RpPb+O9r7cwS8Po6P0f/XtdDAAAAAB+ZvAy5I14Y96EN+XNeHPe
grfs+R0AAAAAwF96ApwhgT4=
""".decode("base64").decode("zlib")



class SortHeadersTest(unittest.TestCase):
	"""tests for sortHeaders.
	"""
	def assertHeaderSequence(self, hdr, keySeq):
		for expected, card in zip(keySeq, hdr.ascardlist()):
			self.assertEqual(expected, card.key)

	def testHeadersPreserved(self):
		"""tests for sortHeaders preserving the incoming headers by default.
		"""
		with testhelpers.testFile("test.fits", _fitsData) as ff:
			hdr = fitstools.sortHeaders(pyfits.open(ff)[0].header)
			self.assertHeaderSequence(hdr, ["SIMPLE", "BITPIX", "NAXIS", "NAXIS1", 
					"NAXIS2", "EXTEND",])
	
	def testWithCommentsAndHistory(self):
		"""tests for sortHeaders sorting comment and history cards.
		"""
		with testhelpers.testFile("test.fits", _fitsData) as ff:
			hdr = pyfits.open(ff)[0].header
			hdr.add_comment("Foo1")
			hdr.add_history("this header added for testing")
			hdr.add_comment("This is at the end.")
			hdr = fitstools.sortHeaders(hdr)
			self.assertHeaderSequence(hdr, ["SIMPLE", "BITPIX", "NAXIS", "NAXIS1", 
					"NAXIS2", "EXTEND", "", "HISTORY", "", "COMMENT", "COMMENT"])

	def testCommentFilter(self):
		"""tests for deletion of unwanted comment cards.
		"""
		with testhelpers.testFile("test.fits", _fitsData) as ff:
			hdr = pyfits.open(ff)[0].header
			hdr.add_comment("to delete")
			hdr.add_comment("keep this one")
			hdr.add_comment("and delete this")
			hdr.add_comment("and also delete this")
			hdr.add_comment("but keep this")
			hdr = fitstools.sortHeaders(hdr, 
				lambda arg: "delete" in arg)
			self.assertHeaderSequence(hdr, ["SIMPLE", "BITPIX", "NAXIS", "NAXIS1", 
					"NAXIS2", "EXTEND", "", "COMMENT", "COMMENT"])
	
	def testOrder(self):
		"""tests for ordering of critical keywords.
		"""
		hdr = pyfits.PrimaryHDU().header
		hdr.update("NAXIS1", 200)
		hdr.update("NAXIS2", 400)
		# EXTEND is now before NAXIS1
		hdr = fitstools.sortHeaders(hdr)
		self.assertHeaderSequence(hdr, ["SIMPLE", "BITPIX", "NAXIS", "NAXIS1", 
			"NAXIS2", "EXTEND"])
		hdr = pyfits.PrimaryHDU().header
		del hdr["EXTEND"]
		hdr.update("NAXIS1", 200)
		hdr.update("FLOB", "Worong")
		hdr.update("EXTEND", "F")
		# EXTEND is now way behind NAXIS1
		hdr = fitstools.sortHeaders(hdr)
		self.assertHeaderSequence(hdr, ["SIMPLE", "BITPIX", "NAXIS", "NAXIS1", 
			"EXTEND", "FLOB"])


class FITSWriteTest(testhelpers.VerboseTest):
	"""tests for correct FITS writing.
	"""
	def _assertOverwriteWorks(self, inFileName):
		hdr = pyfits.open(inFileName)[0].header
		hdr.update("TELESCOP", "Python Telescope")
		hdr.update("APERTURE", 23)
		fitstools.replacePrimaryHeaderInPlace(inFileName, hdr)
		hdu = pyfits.open(inFileName)[0]
		self.assertEqual(hdu.header["TELESCOP"], "Python Telescope")
		self.assertEqual(hdu.header["BITPIX"], 32)
		self.assertEqual(hdu.header["NAXIS1"], 10)
		self.assertEqual(hdu.data[1][4], 4)

	def testInPlaceSameSize(self):
		with testhelpers.testFile("test.fits", _fitsData) as ff:
			self._assertOverwriteWorks(ff)

	def testInPlaceGZ(self):
		with testhelpers.testFile("test.fits.gz", _fitsData, writeGz=True) as ff:
			self.assertRaisesWithMsg(NotImplementedError,
				"replacePrimaryHeaderInPlace no longer supports gzipped files.",
				fitstools.replacePrimaryHeaderInPlace,
				(ff, None))

	def testInPlaceLonger(self):
		with testhelpers.testFile("test.fits", _fitsData) as ff:
			hdr = pyfits.open(ff)[0].header
			for num in range(50):
				hdr.update("KEY%d"%num, num)
			fitstools.replacePrimaryHeaderInPlace(ff, hdr)
			hdu = pyfits.open(ff)[0]
			self.assertEqual(hdu.header["NAXIS1"], 10)
			self.assertEqual(hdu.header["KEY48"], 48)
			self.assertEqual(hdu.data[1][4], 4)

	def testInPlaceShorter(self):
		with testhelpers.testFile("test.fits", _fitsData) as ff:
			hdr = pyfits.open(ff)[0].header
			oldhdr = hdr.copy()
			for num in range(50):
				hdr.update("KEY%d"%num, num)
			fitstools.replacePrimaryHeaderInPlace(ff, hdr)
			fitstools.replacePrimaryHeaderInPlace(ff, oldhdr)
			
			# if things have worked, there's now >= 50 cards of padding
			# in the header, and the end card is in the second after
			# all the padding
			with open(ff) as f:
				firstBlock = f.read(fitstools.FITS_BLOCK_SIZE)
				self.failIf(fitstools.END_CARD in firstBlock)
				secondBlock = f.read(fitstools.FITS_BLOCK_SIZE)
				self.failUnless(fitstools.END_CARD in secondBlock)
				self.failUnless(secondBlock.startswith(" "*2000))

			hdu = pyfits.open(ff)[0]
			self.assertEqual(hdu.header["NAXIS1"], 10)
			self.assertEqual(hdu.data[1][4], 4)
			self.assertRaises(KeyError, lambda: hdu.header["KEY48"])


class ParseCardsTest(testhelpers.VerboseTest):
	def testFailsForJunk(self):
		self.assertRaises(ValueError, fitstools.parseCards, "jfkdl")
	
	def testParses(self):
		input = ("NAXIS1  =                22757 / length of data axis 1       "
			"                   NAXIS2  =                22757 / length of data a"
			"xis 2                          CTYPE1  = 'RA---TAN-SIP'       / TAN "
			"(gnomic) projection + SIP distortions      CTYPE2  = 'DEC--TAN-SIP' "
			"      / TAN (gnomic) projection + SIP distortions      ")
		cards = fitstools.parseCards(input)
		for card, (exKey, exVal) in zip(cards, [
				("NAXIS1", 22757),
				("NAXIS2", 22757),
				("CTYPE1", "RA---TAN-SIP"),
				("CTYPE2", "DEC--TAN-SIP"),]):
			self.assertEqual(card.key, exKey)
			self.assertEqual(card.value, exVal)
	
	def testEndCard(self):
		input = ("NAXIS1  =                22757 / length of data axis 1       "
			"                   NAXIS2  =                22757 / length of data a"
			"xis 2                          END                                  "
			"                                           CTYPE2  = 'DEC--TAN-SIP' "
			"      / TAN (gnomic) projection + SIP distortions      ")
		self.assertEqual(len(fitstools.parseCards(input)), 2)

	def testEmptyCardIgnored(self):
		input = ("NAXIS1  =                22757 / length of data axis 1       "
			"                   NAXIS2  =                22757 / length of data a"
			"xis 2                                                               "
			"                                           CTYPE2  = 'DEC--TAN-SIP' "
			"      / TAN (gnomic) projection + SIP distortions      ")
		self.assertEqual(len(fitstools.parseCards(input)), 3)


class ScalingTest(testhelpers.VerboseTest):

	def _getExFits(self):
		return os.path.join(base.getConfig("inputsDir"), "data", "ex.fits")

	def testIterRowsBscale(self):
		with open(self._getExFits()) as f:
			hdr = fitstools.readPrimaryHeaderQuick(f)
			colIter = fitstools.iterFITSRows(hdr, f)
				
			col = colIter.next()
			self.assertEqual(len(col), 12)
			self.assertEqual(col[-1], 8472.)
			self.assertEqual(len(list(colIter)), 22)

	def testIterScaledRows2(self):
		pixelRows = list(fitstools.iterScaledRows(open(self._getExFits()), 2))
		self.assertEqual(len(pixelRows), 11)
		self.assertEqual(len(pixelRows[0]), 6)
		self.assertEqual(pixelRows[0][-1], 8227.75)

	def testIterScaledRows5(self):
		pixelRows =  list(fitstools.iterScaledRows(open(self._getExFits()), 5))
		self.assertEqual(len(pixelRows), 4)
		self.assertEqual(len(pixelRows[0]), 2)
		self.assertEqual(int(pixelRows[0][-1]), 8621)


class ReadHeaderTest(testhelpers.VerboseTest):
	def testMaxBlocks(self):
		with testhelpers.testFile("bad.fits", " "*8000) as inName:
			self.assertRaisesWithMsg(fitstools.FITSError,
				'No end card found within 2 blocks',
				fitstools.readHeaderBytes,
				(open(inName), 2))

	def testPrematureEOF(self):
		with testhelpers.testFile("bad.fits", " "*80) as inName:
			self.assertRaisesWithMsg(EOFError,
				'Premature end of file while reading header',
				fitstools.readHeaderBytes,
				(open(inName),))


if __name__=="__main__":
	testhelpers.main(ReadHeaderTest)
