# A testbed for developing the pixel scaling algorithm.

import math

def scale(source, nDestX):
	nSourceX = len(source)
	scaled = [0]*nDestX

	for x in range(len(source)):
		loBoundX = float(x)/(nSourceX)*(nDestX);
		upBoundX = float(x+1)/(nSourceX)*(nDestX);
		xDestInd = int(math.floor(loBoundX))
		xDestWeight = 1;
		xDest1Weight = 0;
		rightPart = xDestInd+1-loBoundX
		leftPart = upBoundX-(xDestInd+1)
		if leftPart>1e-9:
			xDestWeight = rightPart/(rightPart+leftPart)
			xDest1Weight = leftPart/(rightPart+leftPart)

		print "\t".join(str(u) for u in (x, xDestInd, xDestWeight, xDest1Weight, loBoundX, upBoundX))
		scaled[xDestInd] += source[x]*xDestWeight
		if xDest1Weight:
			scaled[xDestInd+1] += source[x]*xDest1Weight

	return scaled


if __name__=="__main__":
	print scale([1]*7, 5)
