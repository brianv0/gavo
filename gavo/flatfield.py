"""
This code does a simple flatfielding for astronomical CCD images.

I do a quick hack for the Maidanak data first -- maybe it'll have to
grow as more data comes in.

The x axis corresponds to the second index for these images.
"""

import os
import sys
import optparse
import operator
import pyfits
import numarray
import numarray.ieeespecial


def parseCmdLine():
	"""returns the options and positional arguments in the current command
	line.
	"""
	def parseOverscan(val):
		"""returns a list of slices for numarray.
		"""
		return [":,:17", ":,-12:"]

	parser = optparse.OptionParser(
		usage="usage: %prog <flatfield> <image> {<image>}")
	parser.add_option("-d", "--dark-geometry", help="specify location of"
		" overscan region(s)",
		dest="overscan", default="v20")
	options, args = parser.parse_args()
	options.overscan = parseOverscan(options.overscan)
	options.imageRegion = ":,18:-13"
	if len(args)<2:
		parser.print_help()
		sys.exit(1)
	return options, args[0], args[1:]


class ImageDescriptor:
	"""is a class that specifies the geometry of an image.

	In particular, it knows the overscan regions and the image region,
	and it knows some things one can do with them.

	The regions are currently specified as numarray slices.  This may
	not be a good idea in the long run, but never mind for now.

	It operates on numarray images.
	"""
	def __init__(self, imageRegion, overscanRegions):
		self.imageRegion = imageRegion
		self.overscanRegions = overscanRegions

	def getRegion(self, image, region):
		"""returns a slice from image.

		region specifies a slice; we do this q'n'd here at first; just give any
		valid numpy slice expression in a string here.
		"""
		return eval("arr[%s]"%region, {"arr": image})

	def getOverscanPixels(self, image):
		return numarray.concatenate([numarray.ravel(self.getRegion(image, region))
			for region in self.overscanRegions])
	
	def getImageData(self, image):
		return self.getRegion(image, self.imageRegion)


def correctForDarkCurrent(img, imageDesc):
	"""substracts off the dark current (as determined from overscanRegions)
	from img.
	"""
	darkCurrent = imageDesc.getOverscanPixels(img).mean()
	img -= int(darkCurrent)
	return imageDesc.getImageData(img)


def renormalizeToInt(img, maxVal):
	img[numarray.ieeespecial.getinf(img)] = 0
	scaler = maxVal/float(max(numarray.ravel(img)))
	return numarray.array(img*scaler, type=numarray.Int32)


def loadImage(path, imageDesc):
	"""returns a dark-current corrected hdu list for path.
	"""
	hdus = pyfits.open(path)
	hdus[0].data = correctForDarkCurrent(hdus[0].data, imageDesc)
	return hdus


def doFlatfield(flat, hdus, imageDesc):
	img = correctForDarkCurrent(hdus[0].data, imageDesc)
	newMax = flat.mean()
	img = renormalizeToInt(img/flat, newMax)
	hdus[0].data = img
	hdus[0].header["datamax"] = newMax
	hdus[0].header["datamin"] = min(numarray.ravel(img))
	hdus[0].header["naxis1"] = img.shape[1]
	hdus[0].header["naxis2"] = img.shape[0]


def main():
	opts, flatPath, imgPaths = parseCmdLine()
	imageDesc = ImageDescriptor(opts.imageRegion, opts.overscan)
	flat = loadImage(flatPath, imageDesc)[0].data
	for imgPath in imgPaths:
		doFlatfield(flat, pyfits.open(imgPath), imageDesc)
		hdus.writeto("flatted_"+imgPath)

if __name__=="__main__":
	main()
