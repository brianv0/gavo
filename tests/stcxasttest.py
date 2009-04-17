"""
Tests for parsing STC-X into ASTs.

"""

import bz2
import datetime

from gavo import stc
from gavo.stc import dm

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
			self.asf = stc.parseSTCX(_unwrapSample(self.data))


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
		frame = self.asf[0].astroSystem.timeFrame
		self.assertEqual(frame.timeScale, "TT")
		self.assertEqual(frame.refPos.standardOrigin, "TOPOCENTER")
	
	def testSpaceFrame(self):
		frame = self.asf[0].astroSystem.spaceFrame
		self.assertEqual(frame.flavor, "SPHERICAL")
		self.assertEqual(frame.nDim, 3)
		self.assertEqual(frame.refPos.standardOrigin, "TOPOCENTER")
		frame = self.asf[1].astroSystem.spaceFrame
		self.assertEqual(frame.flavor, "SPHERICAL")
		self.assertEqual(frame.nDim, 2)
		self.assertEqual(frame.refFrame, 'ICRS')
		self.assertEqual(frame.refPos.standardOrigin, "TOPOCENTER")

	def testSimplePlace(self):
		p = self.asf[0].place
		self.assertEqual(p.unit, ("deg", "deg", "m"))
		self.assertAlmostEqual(p.value[0], 248.4056)
		self.assertEqual(p.value[2], 2158.)
		self.failUnless(p.frame is self.asf[0].astroSystem.spaceFrame,
			"Wrong frame on positions")

	def testComplexPlaces(self):
		p = self.asf[1].place
		self.assertEqual(p.unit, ("deg", "deg"))
		self.assertAlmostEqual(p.value[0], 148.88821)
		self.assertAlmostEqual(p.resolution.values[0][1], 0.00025)
		self.assertAlmostEqual(p.pixSize.values[0][1], 0.0001)
		self.assertAlmostEqual(p.error.radii[0], 0.0003)
		self.failUnless(p.frame is self.asf[1].astroSystem.spaceFrame,
			"Wrong frame on complex places")

	def testTime(self):
		p = self.asf[1].time
		self.assertEqual(p.unit, "s")
		self.assertEqual(p.value, datetime.datetime(2004, 7, 15, 8, 23, 56))
		self.assertEqual(p.resolution.values[0], 1000.0)
		self.assertEqual(p.pixSize.values[0], 1000.0)
		self.failUnless(p.frame is self.asf[1].astroSystem.timeFrame,
			"Wrong frame on time.")

	def testSpectral(self):
		p = self.asf[1].freq
		self.assertEqual(p.unit, "Angstrom")
		self.assertEqual(p.value, 4600.)
		self.assertEqual(p.resolution.values[0], 400.0)
		self.assertEqual(p.pixSize.values[0], 400.0)
		self.failUnless(p.frame is self.asf[1].astroSystem.spectralFrame,
			"Wrong frame on spectral.")
	
	def testTimeInterval(self):
		p = self.asf[1].timeAs[0]
		self.assertEqual(p.lowerLimit, datetime.datetime(2004, 7, 15, 8, 17, 36))
		self.assertEqual(p.upperLimit, datetime.datetime(2004, 7, 15, 8, 30, 16))
		self.failUnless(p.frame is self.asf[1].astroSystem.timeFrame,
			"Wrong frame on time interval.")
	
	def testSpectralInterval(self):
		p = self.asf[1].freqAs[0]
		self.assertEqual(p.lowerLimit, 4400.)
		self.assertEqual(p.upperLimit, 4800.)
		self.failUnless(p.frame is self.asf[1].astroSystem.spectralFrame,
			"Wrong frame on spectral interval.")

	def testSpaceInterval(self):
		p = self.asf[1].areas[0]
		self.assertAlmostEqual(p.lowerLimit[0], 148.18821)
		self.assertAlmostEqual(p.upperLimit[1], 69.31529)
		self.failUnless(p.frame is self.asf[1].astroSystem.spaceFrame,
			"Wrong frame on space interval.")


class ChandraResTest(XMLSrcTestBase):
	"""tests on the Chandra resource profile example.
	"""
	data = (    
    'QlpoOTFBWSZTWXXPk0MAAhHfgGAicuf//69332C/79/xUAV+dhrEm1baakVq00Ek'
    'gImNTTKaGnqp+mUn6mTGomm0A1Gj9KP1T1PUNDjJk00wmRkDAjE0YIwg0aYABBKa'
    'JqBpFNgk9TI9R6I9CBoNAGgAaNDjJk00wmRkDAjE0YIwg0aYABBIkTFNJmUNMTUZ'
    'NGmQAZNAaB6gAMCSSbQkTSSTE0xMGMGwaE2CYMGm2CbQMGCaYhHELOL7bcd06We+'
    'qTBa0M4MP8HYa46G1H16ViT9j5QL+xL4lCYKm6+CeROvZtIcK2/l56d3jld28JtK'
    'M+SNZe+vlNBL5R3Pm0WhkRh+EM1U8GjHB87+dz2fXVb5eUsMeaTzHe601323uozb'
    'aUt3ma7J2plHM4qthppjHNPBOPfeQ8Sx77zU5vzQv15YxsO9ROU28k4d8gU6vWih'
    '0qzhwhbcRPxBe0F6xdTKwcufq9tULLuLMpd7Mn0xnwnaNhr77E3zaYCQM/drGT08'
    'm5RW9Lq2eOLnG0QqDIC753+BZSAvUecET93DDx0N3uw8QOJaQsYomXltuREJLXKb'
    'U4JNLJu2mHEhTgRWvUFkkIQSPs9j0SmdAdUmEmEW6KtjbbPIYCEeY50LBp2ZQz3k'
    'yKke56tCMdwOMsEvhLzh19wjwTKKPjWOL8dPYzNOcbZlcSDzoeBkRcDwYTMJOYQO'
    '5rKdgdm6EMHq00F66ev3u2yJbIrlIkksKFS2LYkV8w3PdbbMq93XAJJFiLoTh0rl'
    'o9cRXvUfLjaFiURAFebj0jxpNpGZJvWMgYzb1JomboUOsWY3FctvOZcrTU7asQf9'
    'Sl7ZXJ8GlMaPjxRn6WaqrLyRxUBQE8KLOvgfO4dqTNlsmim8bgaUagpVgwpMZpRr'
    'J/MoQ9d5OZATBznEufCjnMzNJzsjEPkxgHkuM1o2K07S5mUwceTW6pAkkrmuzyho'
    'aVvhwGnkNDbi7Gjv6to8p39AV+g+IK8sod7aaOkLHVwhNMaYtli1A82OI6YOeuZl'
    'Y33momJ7FVoqwvi8zOZaxtPQbx6OYM6Z5dA6niweVqCLUpNT1K5LSphVZAMCKhsJ'
    'kGSCGoKVBpWGstxYKkyk5Y6DK8tZyzshFDO4lQSsURSk9YTCohiBOnEDuzpA4yTG'
    'xjP6larwFwAX5nKcGJu9YTJhYeIWdCy72ZJrKRvQGLWt1mYxbYwywI7gV32XW7oT'
    'SmQWJ0zO1Q4jJohuVJMhI79GILvFxMjOeknExIrgPXs5kXN5wB+MKB3U9F+udPJd'
    '25IxaG0FkW1YhAZDAgqpBxlnqO4Cv0jRFXuLjbGX9oZAElgcHIpjZkgjlIqSY6AG'
    '3ehXtNG/O1msYEmSGQE3jpBibWabrBBMEOkhJkmqbJ2pAhnQbxULO4Ii6CgPKYl3'
    'nBnJpVwsj0mdzehlBa9+knqSUVNPsQi6uQ24JCYtq9DEMWILROZMzKOYlepX3ykk'
    '+FMaWjZslMzLU0Gw1VVgd4rQnBRAmCbWQiHdslAGiViwWKwYM5W7YAnEkCTXiuNf'
    'DGb/UhXo25uab9eyFqKsPOHQs9wzGruUB3JFUiVIXUMnhtHYUhuX7Ig/IXWO1YVk'
    'gKEB7qZ9owRJszRmQRhQHnJ0WgSLVJFMhMdwxxADmrEEbupKYFhZlvpYBZd968yK'
    'ypXBpiku1cs1LACYOHuGs7UurQFIkEq8zIwPBxEqNDJ2WcvWvCj92JE53jGo51pB'
    'Z//F3JFOFCQdc+TQwA==')

	def testTimeCoord(self):
		p = self.asf[0].time
		self.assertEqual(p.frame.timeScale, "TT")
		self.assertEqual(p.unit, "s")
		self.assertAlmostEqual(p.error.values[0], 0.000005)
		self.assertAlmostEqual(p.error.values[1], 0.0001)
		self.assertAlmostEqual(p.resolution.values[0], 0.000016)
		self.assertAlmostEqual(p.resolution.values[1], 3.)
		self.assertAlmostEqual(p.size.values[0], 1000.)
		self.assertAlmostEqual(p.size.values[1], 170000.)

	def testPosition(self):
		p = self.asf[0].place
		self.assertEqual(p.frame.refPos.standardOrigin, "TOPOCENTER")
		self.assertEqual(p.frame.nDim, 2)
		self.assertEqual(p.frame.flavor, "SPHERICAL")
		self.assertEqual(p.unit, ("arcsec", "arcsec"))
		self.assertEqual(p.error.radii[0], 1.)
		self.assertEqual(p.resolution.radii[0], 0.5)
		self.assertEqual(p.size.values[0], (1000, 1000))
		self.assertEqual(p.size.values[1], (4000, 4000))
	
	def testSpectral(self):
		p = self.asf[0].freq
		self.assertEqual(p.unit, "keV")
		self.assertAlmostEqual(p.error.values[0], 0.1)
		self.assertAlmostEqual(p.resolution.values[0], 0.02)
		self.assertAlmostEqual(p.resolution.values[1], 2.)
		self.assertEqual(p.size.values[0], 2.)
		self.assertEqual(p.size.values[1], 10.)

	def testTimeInterval(self):
		p = self.asf[0].timeAs[0]
		self.assertEqual(p.frame, self.asf[0].astroSystem.timeFrame)
		self.assertEqual(p.upperLimit, None)
		self.assertEqual(p.lowerLimit, datetime.datetime(1999, 7, 23, 16, 0))
	
	def testAreas(self):
		p = self.asf[0].areas[0]
		self.assertEqual(p.frame, self.asf[0].astroSystem.spaceFrame)
		self.failUnless(isinstance(p, dm.AllSky))
		self.assertAlmostEqual(p.fillFactor, 0.02)

	def testSpectralInterval(self):
		p = self.asf[0].freqAs[0]
		self.assertEqual(p.frame, self.asf[0].astroSystem.spectralFrame)
		self.assertAlmostEqual(p.lowerLimit, 0.12)
		self.assertAlmostEqual(p.upperLimit, 10)


class GeometriesTest(testhelpers.VerboseTest):
	def _getAST(self, geo):
		return stc.parseSTCX(('<ObservationLocation xmlns="%s">'%stc.STCNamespace)+
			'<AstroCoordSystem id="x">'
			'<SpaceFrame><ICRS/></SpaceFrame>'
			'</AstroCoordSystem><AstroCoordArea coord_system_id="x">'+
			geo+
			'</AstroCoordArea></ObservationLocation>')[0]

	def testCircle(self):
		ast = self._getAST("<Circle><Center><C1>15</C1><C2>40</C2></Center>"
			"<Radius>3</Radius></Circle>")
		p = ast.areas[0]
		self.failUnless(isinstance(p, dm.Circle))
		self.assertEqual(p.radius, 3.0)
		self.assertEqual(p.center, (15.0, 40.0))
	
	def testEllipse(self):
		ast = self._getAST("<Ellipse><Center><C1>10</C1><C2>12</C2></Center>"
			'<SemiMajorAxis>3</SemiMajorAxis><SemiMinorAxis>2</SemiMinorAxis>'
			'<PosAngle unit="rad">1</PosAngle></Ellipse>')
		p = ast.areas[0]
		self.failUnless(isinstance(p, dm.Ellipse))
		self.assertEqual(p.center, (10.0, 12.0))
		self.assertEqual(p.smajAxis, 3.0)
		self.assertEqual(p.sminAxis, 2.0)
		self.assertEqual(p.posAngle, 57.295779513082323)
	
	def testBox(self):
		ast = self._getAST("<Box><Center><C1>10</C1><C2>12</C2></Center>"
			'<Size><C1>1</C1><C2>1.5</C2></Size></Box>')
		p = ast.areas[0]
		self.failUnless(isinstance(p, dm.Box))
		self.assertEqual(p.center, (10.0, 12.0))
		self.assertEqual(p.boxsize, (1.0, 1.5))
	
	def testPolygon(self):
		ast = self._getAST("<Polygon><Vertex><C1>10</C1><C2>12</C2></Vertex>"
			'<Vertex><C1>1</C1><C2>1.5</C2></Vertex></Polygon>')
		p = ast.areas[0]
		self.failUnless(isinstance(p, dm.Polygon))
		self.assertEqual(p.vertices, ((10., 12.), (1., 1.5)))
	
	def testConvex(self):
		ast = self._getAST("<Convex>"
			'<Halfspace><Vector><C1>10</C1><C2>12</C2><C3>1</C3></Vector>'
			'<Offset>0.125</Offset></Halfspace>'
			'<Halfspace><Vector><C1>-10</C1><C2>-12</C2><C3>-1</C3></Vector>'
			'<Offset>-0.125</Offset></Halfspace>'
			'</Convex>')
		p = ast.areas[0]
		self.failUnless(isinstance(p, dm.Convex))
		self.assertEqual(p.vectors, 
			((10.0, 12.0, 1.0, 0.125), (-10.0, -12.0, -1.0, -0.125)))


class UnitsTest(testhelpers.VerboseTest):
	def _getAST(self, frame, coo):
		return stc.parseSTCX(('<ObservationLocation xmlns="%s">'%stc.STCNamespace)+
			'<AstroCoordSystem id="x">%s'
			'</AstroCoordSystem><AstroCoordArea coord_system_id="x">'+
			coo+
			'</AstroCoordArea></ObservationLocation>')[0]

	def testSimpleCoo(self):
		ast = self._getAST("<TimeFrame/>",
			'<Time unit="a">2003-03-03T03:04:05</Time>')
		self.assertEqual(ast.time.unit, "a")
	
	def testSpatial2DEmpty(self):
		ast = self._getAST("<SpaceFrame><ICRS/></SpaceFrame>",
			'<Position2D unit="deg"/>')
		self.assertEqual(ast.place.unit, ("deg", "deg"))

	def testSpatial2DMixed(self):
		ast = self._getAST("<SpaceFrame><ICRS/></SpaceFrame>",
			'<Position2D unit="deg"><Value2><C1 pos_unit="deg">1</C1><C2 pos_unit="arcsec"'
			'>2</C2></Value2></Position2D>')
		self.assertEqual(ast.place.unit, ("deg", "arcsec"))


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
		testhelpers.main(ChandraResTest)
