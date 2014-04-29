"""
Some miscellaneous helpers for making images and such.

As this is a fairly expensive import, this should *not* be imported by
utils.__init__.   Hence, none of these functions are in gavo.api or 
gavo.utils.
"""

from cStringIO import StringIO

import Image
import numpy


def jpegFromNumpyArray(pixels, gamma=0.25):
	"""returns a normalized JPEG for numpy pixels.

	pixels is assumed to come from FITS arrays, which are flipped wrt to
	jpeg coordinates, which is why we're flipping here.

	The normalized intensities are scaled by v^gamma; we believe the default
	helps with many astronomical images 
	"""
	pixels = numpy.flipud(pixels)
	pixMax, pixMin = numpy.max(pixels), numpy.min(pixels)
	pixels = numpy.asarray(numpy.power(
		(pixels-pixMin)/(pixMax-pixMin), gamma)*255, 'uint8')
	f = StringIO()
	Image.fromarray(pixels).save(f, format="jpeg")
	return f.getvalue()
