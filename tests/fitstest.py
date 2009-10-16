"""
Tests for fits helpers
"""

import cStringIO
import os
import shutil
import tempfile
import unittest


from gavo.utils import fitstools
from gavo.utils import pyfits


import testhelpers


_fitsgz1 = \
"""eJzt0b0KwjAUhmH/f+7i3IFWZwfFCgEthXboGm0LHZpIUofevaeIuCRIwUm+B76teTnQRFzic0i0
I4eUVnTTqtSmttRoOok0IdtIlUuTux4QHUQai8zd2264J42RLeWykdS098Jd+Yj2mUjIc1/XU4/6
WhjS5btc1YWylVbW3wvcvWD97RpPb+O9r7cwS8Po6P0f/XtdDAAAAAB+ZvAy5I14Y96EN+XNeHPe
grfs+R0AAAAAwF96ApwhgT4=
""".decode("base64")


class TempFits(object):
	name = "temp.fits"
	def __init__(self, data, name=None):
		if name:
			self.name = name
		self.dir = tempfile.mkdtemp()
		self.path = os.path.join(self.dir, self.name)
		f = open(self.path, "w")
		f.write(data)
		f.close()

	def cleanup(self):
		self.__del__()

	def __del__(self):
		if self.dir:
			shutil.rmtree(self.dir, ignore_errors=True)
		self.dir = None


class SortHeadersTest(unittest.TestCase):
	"""tests for sortHeaders.
	"""
	def assertHeaderSequence(self, hdr, keySeq):
		for expected, card in zip(keySeq, hdr.ascardlist()):
			self.assertEqual(expected, card.key)

	def testHeadersPreserved(self):
		"""tests for sortHeaders preserving the incoming headers by default.
		"""
		tf = TempFits(_fitsgz1.decode("zlib"))
		try:
			hdr = fitstools.sortHeaders(pyfits.open(tf.path)[0].header)
			self.assertHeaderSequence(hdr, ["SIMPLE", "BITPIX", "NAXIS", "NAXIS1", 
					"NAXIS2", "EXTEND",])
		finally:
			tf.cleanup()
	
	def testWithCommentsAndHistory(self):
		"""tests for sortHeaders sorting comment and history cards.
		"""
		tf = TempFits(_fitsgz1.decode("zlib"))
		try:
			hdr = pyfits.open(tf.path)[0].header
			hdr.add_comment("Foo1")
			hdr.add_history("this header added for testing")
			hdr.add_comment("This is at the end.")
			hdr = fitstools.sortHeaders(hdr)
			self.assertHeaderSequence(hdr, ["SIMPLE", "BITPIX", "NAXIS", "NAXIS1", 
					"NAXIS2", "EXTEND", "", "HISTORY", "", "COMMENT", "COMMENT"])
		finally:
			tf.cleanup()

	def testCommentFilter(self):
		"""tests for deletion of unwanted comment cards.
		"""
		tf = TempFits(_fitsgz1.decode("zlib"))
		try:
			hdr = pyfits.open(tf.path)[0].header
			hdr.add_comment("to delete")
			hdr.add_comment("keep this one")
			hdr.add_comment("and delete this")
			hdr.add_comment("and also delete this")
			hdr.add_comment("but keep this")
			hdr = fitstools.sortHeaders(hdr, 
				lambda arg: "delete" in arg)
			self.assertHeaderSequence(hdr, ["SIMPLE", "BITPIX", "NAXIS", "NAXIS1", 
					"NAXIS2", "EXTEND", "", "COMMENT", "COMMENT"])
		finally:
			tf.cleanup()
	
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


class FITSWriteTest(unittest.TestCase):
	"""tests for correct FITS writing.
	"""
	def test(self):
		"""tests for in-place operation of header replacement.
		"""
		tf = TempFits(_fitsgz1.decode("zlib"), "input.fits")
		try:
			hdr = pyfits.open(tf.path)[0].header
			hdr.update("TELESCOP", "Python Telescope")
			hdr.update("APERTURE", 23)
			fitstools.replacePrimaryHeaderInPlace(tf.path, hdr)
			hdu = pyfits.open(tf.path)[0]
			self.assertEqual(hdu.header["TELESCOP"], "Python Telescope")
			self.assertEqual(hdu.header["BITPIX"], 32)
			self.assertEqual(hdu.header["NAXIS1"], 10)
			self.assertEqual(hdu.data[1][4], 4)
		finally:
			tf.cleanup()


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


if __name__=="__main__":
	testhelpers.main(ParseCardsTest)

