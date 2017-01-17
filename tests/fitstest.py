"""
Tests for fits helpers
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import cStringIO
import os
import re
import shutil
import tempfile
import unittest

from gavo.helpers import testhelpers

from gavo import base
from gavo.helpers import fitstricks
from gavo.utils import fitstools
from gavo.utils import pyfits


_fitsData = \
"""eJzt0b0KwjAUhmH/f+7i3IFWZwfFCgEthXboGm0LHZpIUofevaeIuCRIwUm+B76teTnQRFzic0i0
I4eUVnTTqtSmttRoOok0IdtIlUuTux4QHUQai8zd2264J42RLeWykdS098Jd+Yj2mUjIc1/XU4/6
WhjS5btc1YWylVbW3wvcvWD97RpPb+O9r7cwS8Po6P0f/XtdDAAAAAB+ZvAy5I14Y96EN+XNeHPe
grfs+R0AAAAAwF96ApwhgT4=
""".decode("base64").decode("zlib")

_nastyHeaderData = \
"""
eJztkctOwzAQRX/lrsgGFbpjwyKUQCOah5pQdesm08TIskvsNCpfj90WCaQWqRLsfOSVH2c8d4o4
yWcRcI8TlKc2f+chLvN4ecZ3d7kvDZdxgTO+28t90bKM0se/63eWpc+LcGZ9QdlyDbsYhJINtkz0
BNMyg4ELgY7ee96RPa6UNFzaw4p1Nbi0lwhrbjSugkmWlnH6aicStMRq6kZAWJmeCbG7dhetQcmK
QFuSGJgrt+qbQx0lxQ66VQPV6DfWBnzzDa19YQZ1rM8MVxKCS9IYnJbVb6wiadyzs0zjaB7OJ1Pk
efiCfPw0Rr6I5kWcpS6D8egwkwA3yJOw2Ld1aARb6rQr+YNJliRRWmIfniF9DKtVG1r3tmfUnDVS
fdjvyZ3NsOlIO4s+5qZdciRq/TVfN1yPx+PxeDyef+QT1lS2XQ==
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

	def testWithCardSequence(self):
		cardsIn = [pyfits.Card(*args) for args in (
			("SIMPLE", True), ("BITPIX", 0), ("NAXIS", 0),
			("BOOKS", "Plenty"), ("CROOKS", 5), ("HOOKS", "None"))]
		hdr = fitstools.sortHeaders(cardsIn,
			cardSequence=(("SIMPLE", True), ("HOOKS", True),
				(pyfits.Card(value="---- Separator ----"), None), 
				("CROOKS", True)))
		self.assertEqual(
			re.sub("  *", lambda mat: "(%d)"%len(mat.group(0)), str(hdr)),
			"SIMPLE(2)=(20)T(50)BITPIX(2)=(20)0(50)NAXIS(3)=(20)0(50)"
			"HOOKS(3)=(1)'None(4)'(68)----(1)Separator(1)----(53)"
			"CROOKS(2)=(20)5(50)BOOKS(3)=(1)'Plenty(2)'(60)END(2317)")

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

	def testWithContinueCards(self):
		hdr = pyfits.Header()
		hdr.update("LONGVAL", "This is a long value that will require a"
			" continue card in the fits header.  Actually, there once even"
			" was a bug that only showed up when two contination lines"
			" were adjacent")
		hdr.add_comment("There were times when the combination of comment"
			" and continue cards were a problem")
		hdr.add_comment("This test will hopefully diagnoze any regressions"
			" in these fields")
		serialized = fitstools.serializeHeader(hdr)
		self.assertEqual(len(serialized), fitstools.FITS_BLOCK_SIZE)
		self.assertEqual(serialized[:9], "LONGVAL =")
		self.assertEqual(serialized[80:89], "CONTINUE ")
		self.assertEqual(serialized[160:169], "CONTINUE ")
		self.assertEqual(serialized[240:249], "COMMENT T")
		self.assertEqual(serialized[320:331], "COMMENT  a ")
		self.assertEqual(serialized[400:409], "COMMENT T")
		self.assertEqual(serialized[480:489], "END      ")

	def testRoundtrip(self):
		with testhelpers.testFile("test.fits", _nastyHeaderData) as ff:
			with open(ff) as f:
				hdr = fitstools.readPrimaryHeaderQuick(f)
			self.assertEqual(fitstools.serializeHeader(hdr),
				_nastyHeaderData)


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

	def testIterScaledRowsSlow(self):
		pixelRows =  list(fitstools.iterScaledRows(
			open(self._getExFits(), "rb"), 5,
			slow=True))
		self.assertEqual(len(pixelRows), 4)
		self.assertEqual(len(pixelRows[0]), 2)
		self.assertEqual(int(pixelRows[0][-1]), 8621)

	def testIterScaledRowsWidth(self):
		pixelRows =  list(fitstools.iterScaledRows(open(self._getExFits()), 
			destSize=5))
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


class FITSCutoutTest(testhelpers.VerboseTest):
	def setUp(self):
		self.origHDU = pyfits.open(os.path.join(base.getConfig("inputsDir"),
			"data", "excube.fits"))[0]

	def testSimpleCutout1(self):
		res = fitstools.cutoutFITS(self.origHDU, (1, 2, 3))
		self.assertEqual(res.header["NAXIS1"], 2)
		self.assertEqual(res.header["CRPIX1"], 36.)
		self.assertEqual(res.header["NAXIS"], 3)
		self.assertEqual(res.header["NAXIS2"], 7)
		self.assertEqual(res.header["CALIFAID"], 935)
		self.assertAlmostEqual(res.data[0][0][0], 0.01679336)
		self.assertAlmostEqual(res.data[-1][-1][-1], -0.01980321)

	def testOpenCutout2(self):
		res = fitstools.cutoutFITS(self.origHDU, (2, -1, 3))
		self.assertEqual(res.header["NAXIS1"], 11)
		self.assertEqual(res.header["NAXIS2"], 3)
		self.assertEqual(res.header["CRPIX2"], 33.)
		self.assertAlmostEqual(res.data[0][0][0], 0.02511436)
		self.assertAlmostEqual(res.data[-1][-1][-1], 0.09358116)

	def testOpenCutout3(self):
		res = fitstools.cutoutFITS(self.origHDU, (3, 3, 10000))
		self.assertEqual(res.header["NAXIS3"], 2)
		self.assertEqual(res.header["CRPIX3"], -1.)
		self.assertAlmostEqual(res.data[0][0][0], 0.03102851)
		self.assertAlmostEqual(res.data[-1][-1][-1], 0.07562912)

	def testMultiCutout(self):
		res = fitstools.cutoutFITS(self.origHDU, (1, 6, 8), (2, 3, 3),
			(3, 2, 4))
		self.assertEqual(res.header["NAXIS1"], 3)
		self.assertEqual(res.header["CRPIX1"], 32)
		self.assertEqual(res.header["NAXIS2"], 1)
		self.assertEqual(res.header["CRPIX2"], 31)
		self.assertEqual(res.header["NAXIS3"], 3)
		self.assertEqual(res.header["CRPIX3"], 0)
		self.assertAlmostEqual(res.data[0][0][0], 0.0155675)
		self.assertAlmostEqual(res.data[-1][-1][-1], 0.05489994)
	
	def testSwappedLimits(self):
		res = fitstools.cutoutFITS(self.origHDU, (1, 8, 7))
		self.assertEqual(res.header["NAXIS1"], 1)
		self.assertAlmostEqual(res.data[0][0][0], -0.01717306)

	def testMinOutOfLimit(self):
		res = fitstools.cutoutFITS(self.origHDU, (1, 13, 15))
		self.assertEqual(res.header["NAXIS1"], 1)
		self.assertAlmostEqual(res.data[0][0][0], 0.0558035)
		self.assertEqual(res.header["CRPIX1"], 27.)

	def testMaxOutOfLimit(self):
		res = fitstools.cutoutFITS(self.origHDU, (1, -13, -12))
		self.assertEqual(res.header["NAXIS1"], 1)
		self.assertAlmostEqual(res.data[0][0][0], 0.02511436)
		self.assertEqual(res.header["CRPIX1"], 37.)


class WCSAxisTest(testhelpers.VerboseTest):
	def testTransformations(self):
		ax = fitstools.WCSAxis("test", 4, 9, 0.5)
		self.assertEqual(ax.pixToPhys(10), 4.5)
		self.assertEqual(ax.physToPix(4.5), 10) 
	
	def testPix0Transformation(self):
		ax = fitstools.WCSAxis("test", 0, -9, -3)
		self.assertEqual(ax.pix0ToPhys(10), -60)
		self.assertEqual(ax.physToPix0(-60), 10)

	def testLimits(self):
		ax = fitstools.WCSAxis("test", -30, 2000, 0.25, axisLength=400)
		self.assertEqual(ax.getLimits(), (-529.75, -430.0))

	def testNoneTrafo(self):
		ax = fitstools.WCSAxis("test", 4, 9, 0.5)
		self.assertEqual(ax.pixToPhys(None), None)
		self.assertEqual(ax.physToPix(None), None) 

	def testNone0Trafo(self):
		ax = fitstools.WCSAxis("test", 4, 9, 0.5)
		self.assertEqual(ax.pix0ToPhys(None), None)
		self.assertEqual(ax.physToPix0(None), None) 


class WCSFromHeaderTest(testhelpers.VerboseTest):

	_baseHdr = {
		"CTYPE1": 'WAVELEN ',
		"CTYPE2": 'RA---TAN',
		"CTYPE3": 'DEC--TAN',
		"CRVAL1":                496.0,
		"CRVAL2":            148.75004,
		"CRVAL3":          -1.50138888,
		"CRPIX1":                    1,
		"CRPIX2":                 32.5,
		"CRPIX3":                    1,
		"CDELT1":                0.269,
		"CDELT2": -2.7777777777777E-05,
		"CDELT3":                  1.0,
		"CUNIT1": 'nm    ',
		"CNAME2": "FOOCOL   "}

	def testMultiDRejected(self):
		hdr = self._baseHdr.copy()
		hdr["PC2_2"] = 23.3
		self.assertRaisesWithMsg(ValueError,
			"FITS axis 2 appears not separable.  WCSAxis cannot handle this.",
			fitstools.WCSAxis.fromHeader,
			(hdr, 2))

	def testNameInferenceCtype(self):
		ax = fitstools.WCSAxis.fromHeader(self._baseHdr, 1)
		self.assertEqual(ax.name, "WAVELEN_1")

	def testNameInferenceCname(self):
		ax = fitstools.WCSAxis.fromHeader(self._baseHdr, 2)
		self.assertEqual(ax.name, "FOOCOL_2")

	def testNameInferenceCleanedCtype(self):
		ax = fitstools.WCSAxis.fromHeader(self._baseHdr, 3)
		self.assertEqual(ax.name, "DEC_3")
	
	def testNameInferenceFallback(self):
		hdr = self._baseHdr.copy()
		del hdr["CTYPE3"]
		ax = fitstools.WCSAxis.fromHeader(hdr, 3)
		self.assertEqual(ax.name, "COO_3")

	def testOtherData(self):
		ax = fitstools.WCSAxis.fromHeader(self._baseHdr, 1)
		self.assertEqual(ax.crval, 496.0)
		self.assertEqual(ax.crpix, 1)
		self.assertEqual(ax.cdelt, 0.269)
		self.assertEqual(ax.cunit, "nm")
		self.assertEqual(ax.ctype, "WAVELEN")

	def testEmptyUnitBecomesNone(self):
		ax = fitstools.WCSAxis.fromHeader(self._baseHdr, 2)
		self.assertEqual(ax.cunit, None)


class ESODescriptorsTest(testhelpers.VerboseTest):
	def testSimple(self):
		descs = fitstools._ESODescriptorsParser("""
			'WSTART'         ,'R*8 '   ,    1,   6,'3E23.15',' ',' '              
  			3.983291748046876E+03  4.011743652343751E+03  4.040604980468751E+03  
  			4.069884765625001E+03  4.099591796875001E+03  4.129735839843751E+03
			'NPTOT'          ,'I*4 '   ,    1,   14,'7I10',' ',' '
       	 	 	 552       556       560       564       568       572       576
       	 	 	 581       585       589       594       598       603       608
      """).result
		self.assertEqual(descs, {
			'WSTART': [3983.291748046876, 4011.743652343751, 4040.604980468751,
				4069.884765625001, 4099.591796875001, 4129.735839843751],
			'NPTOT': [552, 556, 560, 564, 568, 572, 576, 581, 585, 589, 594,
				598, 603, 608],
		})
	
	def testShortArray(self):
		self.assertRaisesWithMsg(base.SourceParseError,
			"At character 199: Expected a float here, offending ''",
			fitstools._ESODescriptorsParser,
			("""
			'WSTART'         ,'R*8 '   ,    1,   6,'3E23.15',' ',' '              
  			3.983291748046876E+03  4.011743652343751E+03  4.040604980468751E+03  
  			4.069884765625001E+03  4.099591796875001E+03""",))

	# Maybe do a test with a real header here?


class _TemplatedHeader(testhelpers.TestResource):
	fitstricks.registerTemplate('dachstest',
		fitstricks.MINIMAL_IMAGE_TEMPLATE+[
			pyfits.Card(value="---- Separator"),
			("ADDLATER", "This is inserted later"),
			("CHGLATER", "This is changed later"),
			("TESTVAL", "Just some random junk"),])

	def make(self, dependents):
		hdr = fitstricks.makeHeaderFromTemplate("dachstest",
			BITPIX=8, NAXIS1=3, NAXIS2=4, TESTVAL="Really",
			CHGLATER=23)

		class _(object):
			fits = hdr
			ser = str(hdr)

		return _

_templatedHeader = _TemplatedHeader()


class _ExtendedTemplatedHeader(testhelpers.TestResource):
	resources = [("base", _templatedHeader)]

	def make(self, dependents):
		base = dependents["base"].fits.copy()
		base.add_history("Changed by someone else")
		base.add_comment("This is snide")
		base.add_comment("Da-te-dum")
		hdr = fitstricks.updateTemplatedHeader(base,
			ADDLATER=42.25, CHGLATER=24)

		class _(object):
			fits = hdr
			ser = str(hdr)

		return _


class TemplatingTest(testhelpers.VerboseTest):
	resources = [("base", _templatedHeader),
		("mod", _ExtendedTemplatedHeader())]
	
	def testParmeterSwallowed(self):
		self.assertEqual(self.base.fits["NAXIS1"], 3)
	
	def testOmittedHeadersOmitted(self):
		self.assertFalse("BZERO" in self.base.fits)
	
	def testHeaderSequence(self):
		self.assertEqual([c.key for c in self.base.fits.ascard],
			['SIMPLE', 'EXTEND', 'BITPIX', 'NAXIS', 'NAXIS1', 'NAXIS2', 
				'', 'CHGLATER', 'TESTVAL', 'HISTORY'])
	
	def testNiceSeparator(self):
		self.assertTrue("2nd axis                      ---- Separator"
			in self.base.ser)
	
	def testCustomComment(self):
		self.assertTrue("'Really  '           / Just some random junk"
			in self.base.ser)
	
	def testCreationHistoryPresent(self):
		self.assertTrue("HISTORY GAVO DaCHS template used: dachstest"
			in self.base.ser)

	def testModifiedHeaderSequence(self):
		self.assertEqual([c.key for c in self.mod.fits.ascard],
			['SIMPLE', 'EXTEND', 'BITPIX', 'NAXIS', 'NAXIS1', 'NAXIS2', 
				'', 'ADDLATER', 'CHGLATER', 'TESTVAL', 'HISTORY', 'HISTORY',
				'', 'COMMENT', 'COMMENT'])
	
	def testUpdateAdds(self):
		self.assertEqual(self.mod.fits["ADDLATER"], 42.25)
	
	def testUpdateChanges(self):
		self.assertEqual(self.base.fits["CHGLATER"], 23)
		self.assertEqual(self.mod.fits["CHGLATER"], 24)

	def testHistoryPreserved(self):
		self.assertTrue("HISTORY Changed by someone else"
			in self.mod.ser)

	def testCommentsPreserved(self):
		self.assertTrue("COMMENT Da-te-dum" in self.mod.ser)


if __name__=="__main__":
	testhelpers.main(WCSFromHeaderTest)
