"""
Some miscellaneous helpers for making images and such.

As this may turn into a fairly expensive import, this should *not* be imported
by utils.__init__.   Hence, none of these functions are in gavo.api or
gavo.utils.
"""

from cStringIO import StringIO

import Image
import numpy


def _normalizeForImage(pixels, gamma):
	"""helps jpegFromNumpyArray and friends.
	"""
	pixels = numpy.flipud(pixels)
	pixMax, pixMin = numpy.max(pixels), numpy.min(pixels)
	return numpy.asarray(numpy.power(
		(pixels-pixMin)/(pixMax-pixMin), gamma)*255, 'uint8')


def jpegFromNumpyArray(pixels, gamma=0.25):
	"""returns a normalized JPEG for numpy pixels.

	pixels is assumed to come from FITS arrays, which are flipped wrt to
	jpeg coordinates, which is why we're flipping here.

	The normalized intensities are scaled by v^gamma; we believe the default
	helps with many astronomical images 
	"""
	f = StringIO()
	Image.fromarray(_normalizeForImage(pixels, gamma)
		).save(f, format="jpeg")
	return f.getvalue()


def colorJpegFromNumpyArrays(rPix, gPix, bPix, gamma=0.25):
	"""as jpegFromNumpyArray, except a color jpeg is built from red, green,
	and blue pixels.
	"""
	pixels = numpy.array([
		_normalizeForImage(rPix, gamma),
		_normalizeForImage(gPix, gamma),
		_normalizeForImage(bPix, gamma)]).transpose(1,2,0)

	f = StringIO()
	Image.fromarray(pixels, mode="RGB").save(f, format="jpeg")
	return f.getvalue()

