"""
Converts a GIMP palette for use with web.jpegrenderer
"""

import itertools
import sys
import re

def getPalStrFromGimp(inF):
	triplePat = re.compile(r"\s+".join(r"(\d+)" for i in range(3)))
	pal = []
	inF.next()  # magic
	inF.next()  # Name

	for ln in inF:
		if ln.startswith("#"):
			continue
		try:
			pal.append(tuple(int(s) for s in triplePat.search(ln).groups()))
		except AttributeError:
			print "Bad line:", ln.strip()
	return "".join(["%s%s%s"%tuple(chr(i) for i in tup) for tup in pal])

def getGradient(startVal, endVal, width):
	slope = float(endVal-startVal)/width
	return [startVal+slope*i for i in range(width)]

def getChannel(tuples, maxVal):
	width = maxVal/len(tuples)
	chanVals = []
	for startVal, endVal in tuples:
		chanVals.extend(getGradient(startVal, endVal, width))
	chanVals.extend([chanVals[-1]]*(maxVal-len(chanVals)))
	return [chr(int(c*maxVal)) for c in chanVals]

def getPalStrFromDs9(redTups, greenTups, blueTups):
	maxVal = 255
	return "".join(["%s%s%s"%(r,g,b) for r,g,b in itertools.izip(
		getChannel(redTups, maxVal),
		getChannel(greenTups, maxVal),
		getChannel(blueTups, maxVal))])

def getRainbow():
	return getPalStrFromDs9([(0,1),(1,0),(0,0),(0,1)], 
		[(0,0),(0,1),(1,0.2),(0.2,0)],
		[(0,0),(0,0),(0,1)])

	
if __name__=="__main__":
#	print repr(getPalStrFromGimp(open(sys.argv[1])))
	print repr(getRainbow())


