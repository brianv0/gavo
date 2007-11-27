"""
Converts a GIMP palette for use with web.jpegrenderer
"""

import sys
import re

def getPalStr(inF):
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

if __name__=="__main__":
	print repr(getPalStr(open(sys.argv[1])))


