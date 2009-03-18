"""
Tests for parsing STC-X into ASTs.

"""

import bz2

from gavo import stc

import testhelpers

def _unwrapSample(samp):
	return bz2.decompress(samp.decode("base64"))


class XMLSrcTestBase(testhelpers.VerboseTest):
	"""A base class for tests on XML data input.

	The input comes as base64-encoded bzip2ed XML in the data attribute.
	The AST resulting from the parse is in the ast attribute.

	You can generate these strings by calling this module with an absolute
	path (the leading slash is important).
	"""
	def __init__(self, *args, **kwargs):
		testhelpers.VerboseTest.__init__(self, *args, **kwargs)
		if hasattr(self, "data"):
			self.ast = stc.parseSTCX(_unwrapSample(self.data))


class M81EventHrefTest(testhelpers.VerboseTest):
	"""The M81 event example with hrefs.
	
	Make this an XMLSrcTestBased test when we grow hrefs.
	"""
	data = (
    'QlpoOTFBWSZTWR0wcQMAAUJfgFVQeAP/968v30C/79/gQAKarDXOnRhJKnpoFH5U'
    '/SQ9JpoGj0gaANNBpoBoJQkyamFNHqepo9Q0GjQDNT1DQNDTagEik1T2pH6SHqHq'
    'D9SaAeoNA0AAAAkiRNGJoNAaRp6QaA0AAaGQ0rQgogbQIYDaEFrEAsAAmvjLYdnr'
    '7/VzvPTQJzceGZ52FelzjIxHQT3UziB5u7eO7LwmYMwa8/NX8hc9GpQIB+KS2yBW'
    'quVK4oUBejQ2LCugvJQ7U5EeDiXThsWUsmTNgwS/U+lDWtVRTCtERDRihXmQc/IK'
    'gbJeU2FAUOrQtUKHtJOhQ2HjiqS4USEWcksAhiIToay9DBX0l6mU7sxMhOhbRsQz'
    'yW3ArFwPxTozlEVZBmlHQlBWHhwZ9ap1cmUfVt1xHwIXStzNkfl/W3TBIkQdZJB6'
    'kgKDweHbNDQ8shZJE7JowGQ0xzY8iaIIaGjxCo3iLUiaqgqvpBzpybz0/1RULfqT'
    'UqqUhoJqKVUX6NIM5VQYPAKTYGIjRsyE4d9tG3IFzGxRLcGeDuwMDfZMZXzKuDQa'
    '8fg6tcK1pe4aShKwpiDBnp0PqHTw5Ba5RjHEtBHUZ1Mh5qZWkk4jf2gJBKFt9VAO'
    'iYhpJLpNrMA7ERKoG4tVijL1gWehETCVtOIjJTWohYCNgwl3kH1CiWUqMKMQo0DE'
    'BIjGajRMVqd5WULkNXipxksrE2hWhEZIKALZjLIhkUq+U0SAv44E6kRKG4MKFFVV'
    'CepRZDaq8ycJHLJNKIhaWlTK4jPWShlUhSuBBOA6iGGAYVKIkYENovlY6kJ1aCEE'
    'bUZhkWIiAzwq8HMycp0016msgGQgf4u5IpwoSA6YOIGA')
	
	def testCooSys(self):
		self.assertRaises(stc.STCNotImplementedError, stc.parseSTCX,
			_unwrapSample(self.data))


class M81ImageTest(XMLSrcTestBase):
	"""The M81 without references sample.
	"""
	data = (
	  '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'
    '4PXco3d+IxDaT/xdyRThQkOE9tcI')
	
	def testTimeFrame(self):
		frame = self.ast.systems[0].timeFrame
		self.assertEqual(frame.timeScale, "TT")
		self.assertEqual(frame.refPos.standardOrigin, "TOPOCENTER")
	
	def testSpaceFrame(self):
		frame = self.ast.systems[0].spaceFrame
		self.assertEqual(frame.flavor, "SPHERICAL")
		self.assertEqual(frame.nDim, 3)
		self.assertEqual(frame.refPos.standardOrigin, "TOPOCENTER")
		frame = self.ast.systems[1].spaceFrame
		self.assertEqual(frame.flavor, "SPHERICAL")
		self.assertEqual(frame.nDim, 2)
		self.assertEqual(frame.refFrame, 'ICRS')
		self.assertEqual(frame.refPos.standardOrigin, "TOPOCENTER")

	def testSimplePlace(self):
		p = self.ast.places[0]
		self.assertEqual(p.unit, "deg deg m")
		self.assertAlmostEqual(p.value[0], 248.4056)
		self.assertEqual(p.value[2], 2158.)
		self.failUnless(p.frame is self.ast.systems[0].spaceFrame,
			"Wrong frame on positions")

	def testComplexPlaces(self):
		p = self.ast.places[1]
		self.assertEqual(p.unit, "deg")
		self.assertAlmostEqual(p.value[0], 148.88821)
		self.assertAlmostEqual(p.resolution[0][1], 0.00025)
		self.assertAlmostEqual(p.pixSize[0][1], 0.0001)


def _wrapSample(srcPath):
	import textwrap
	bzstr = bz2.compress(open(srcPath).read()
		).encode("base64").replace("\n", "")
	print "\n".join("    '%s'"%s for s in textwrap.wrap(bzstr, width=64))


if __name__=="__main__":
	import sys
	if len(sys.argv)>1 and sys.argv[1].startswith("/"):
		_wrapSample(sys.argv[1])
	else:
		testhelpers.main(M81ImageTest)
