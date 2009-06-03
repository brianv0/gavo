"""
Formatting and text manipulation code independent of GAVO code.
"""

import math
import os
import re

from gavo.utils.excs import Error, LiteralParseError

floatRE = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"


def formatSize(val, sf=1):
	"""returns a human-friendly representation of a file size.
	"""
	if val<1e3:
		return "%d Bytes"%int(val)
	elif val<1e6:
		return "%.*fkiB"%(sf, val/1024.)
	elif val<1e9:
		return "%.*fMiB"%(sf, val/1024./1024.)
	else:
		return "%.*fGiB"%(sf, val/1024./1024./1024)


def makeEllipsis(aStr, maxLen):
	if len(aStr)>maxLen:
		return aStr[:maxLen-3]+"..."
	return aStr



def getRelativePath(fullPath, rootPath):
	"""returns rest if fullPath has the form rootPath/rest and raises an
	exception otherwise.
	"""
	if not fullPath.startswith(rootPath):
		raise LiteralParseError(
			"Full path %s does not start with resource root %s"%(fullPath, rootPath),
			None, fullPath)
	return fullPath[len(rootPath):].lstrip("/")


def resolvePath(rootPath, relPath):
	"""joins relPath to rootPath and makes sure the result really is
	in rootPath.
	"""
	relPath = relPath.lstrip("/")
	fullPath = os.path.realpath(os.path.join(rootPath, relPath))
	if not fullPath.startswith(rootPath):
		raise LiteralParseError("I believe you are cheating -- you just tried to"
			" access %s, which I am not authorized to give you."%fullPath,
			None, relPath)
	if not os.path.exists(fullPath):
		raise LiteralParseError(
			"Invalid path %s.  This should not happen."%fullPath, None,
			relPath)
	return fullPath


def formatDocs(docItems, underliner):
	"""returns RST-formatted docs for docItems.

	docItems is a list of (title, doc) tuples.  doc is currently
	rendered in a preformatted block.
	"""
	def formatDocstring(docstring):
		"""returns a docstring with a consistent indentation.

		Rule (1): any whitespace in front of the first line is discarded.
		Rule (2): if there is a second line, any whitespace at its front
		  is the "governing whitespace"
		Rule (3): any governing whitespace in front of the following lines
		  is removed
		Rule (4): All lines are indented by 2 blanks.
		"""
		lines = docstring.split("\n")
		newLines = [lines.pop(0).lstrip()]
		if lines:
			whitespacePat = re.compile("^"+re.match(r"\s*", lines[0]).group())
			for line in lines:
				newLines.append(whitespacePat.sub("", line))
		return "  "+("\n  ".join(newLines))

	docLines = []
	for title, body in docItems:
		docLines.extend([title, underliner*len(title), "", "::", "",
			formatDocstring(body), ""])
	docLines.append("\n.. END AUTO\n")
	return "\n".join(docLines)


def fixIndentation(code, newIndent, governingLine=0):
	"""returns code with all whitespace from governingLine removed from
	every line and newIndent prepended to every line.

	governingLine lets you select a line different from the first one
	for the determination of the leading white space.  Lines before that
	line are left alone.
	>>> fixIndentation("  foo\\n  bar", "")
	'foo\\nbar'
	>>> fixIndentation("  foo\\n   bar", " ")
	' foo\\n  bar'
	>>> fixIndentation("  foo\\n   bar\\n    baz", "", 1)
	'foo\\nbar\\n baz'
	>>> fixIndentation("  foo\\nbar", "")
	Traceback (most recent call last):
	Error: Bad indent in line 'bar'
	"""
	codeLines = [line for line in code.split("\n")]
	reserved, codeLines = codeLines[:governingLine], codeLines[governingLine:]
	if codeLines:
		firstIndent = re.match("^\s*", codeLines[0]).group()
		fixedLines = []
		for line in codeLines:
			if not line.strip():
				fixedLines.append(line)
			else:
				if line[:len(firstIndent)]!=firstIndent:
					raise Error("Bad indent in line %s"%repr(line))
				fixedLines.append(newIndent+line[len(firstIndent):])
	else:
		fixedLines = codeLines
	reserved = [newIndent+l.lstrip() for l in reserved]
	return "\n".join(reserved+fixedLines)


def parsePercentExpression(literal, format):
	"""returns a dictionary of parts in the %-template format.

	format is a template with %<conv> conversions, no modifiers are
	allowed.  Each conversion is allowed to contain zero or more characters
	matched stingily.  Successive conversions without intervening literarls
	are very tricky and will usually not match what you want.  If we need
	this, we'll have to think about modifiers or conversion descriptions ("H
	is up to two digits" or so).

	This is really only meant as a quick hack to support times like 25:33.
	>>> r=parsePercentExpression("12,xy:33,","%a:%b,%c"); r["a"], r["b"], r["c"]
	('12,xy', '33', '')
	>>> r = parsePercentExpression("12,13,14", "%a:%b,%c")
	Traceback (most recent call last):
	LiteralParseError: '12,13,14' cannot be parsed using format '%a:%b,%c'
	"""
	parts = re.split(r"(%\w)", format)
	newReParts = []
	for p in parts:
		if p.startswith("%"):
			newReParts.append("(?P<%s>.*?)"%p[1])
		else:
			newReParts.append(re.escape(p))
	mat = re.match("".join(newReParts)+"$", literal)
	if not mat:
		raise LiteralParseError("'%s' cannot be parsed using format '%s'"%(
			literal, format), None, literal)
	return mat.groupdict()


def parseAssignments(assignments):
	"""returns a name mapping dictionary from a list of assignments.

	This is the preferred form of communicating a mapping from external names
	to field names in records to macros -- in a string that contains
	":"-seprated pairs seperated by whitespace, like "a:b  b:c", where
	the incoming names are leading, the desired names are trailing.

	If you need defaults to kick in when the incoming data is None, try
	_parseDestWithDefault in the client function.

	This function parses a dictionary mapping original names to desired names.

	>>> parseAssignments("a:b  b:c")
	{'a': 'b', 'b': 'c'}
	"""
	return dict([(lead, trail) for lead, trail in
		[litPair.split(":") for litPair in assignments.split()]])


def hmsToDeg(hms, sepChar=" "):
	"""returns the time angle (h m s.decimals) as a float in degrees.

	>>> "%3.8f"%hmsToDeg("22 23 23.3")
	'335.84708333'
	>>> "%3.8f"%hmsToDeg("22:23:23.3", ":")
	'335.84708333'
	>>> "%3.8f"%hmsToDeg("222323.3", "")
	'335.84708333'
	>>> hmsToDeg("junk")
	Traceback (most recent call last):
	LiteralParseError: Invalid time with sepchar ' ': 'junk'
	"""
	hms = hms.strip()
	try:
		if sepChar=="":
			parts = hms[:2], hms[2:4], hms[4:]
		else:
			parts = hms.split(sepChar)
		if len(parts)==3:
			hours, minutes, seconds = parts
		elif len(parts)==2:
			hours, minutes = parts
			seconds = 0
		else:
			raise ValueError("Too many parts")
		timeSeconds = int(hours)*3600+float(minutes)*60+float(seconds)
	except ValueError:
		raise LiteralParseError("Invalid time with sepchar %s: %s"%(
			repr(sepChar), repr(hms)), None, hms)
	return timeSeconds/3600/24*360


def dmsToDeg(dmsAngle, sepChar=" "):
	"""returns the degree minutes seconds-specified dmsAngle as a 
	float in degrees.

	>>> "%3.8f"%dmsToDeg("45 30.6")
	'45.51000000'
	>>> "%3.8f"%dmsToDeg("45:30.6", ":")
	'45.51000000'
	>>> "%3.8f"%dmsToDeg("-45 30 7.6")
	'-45.50211111'
	>>> dmsToDeg("junk")
	Traceback (most recent call last):
	LiteralParseError: Invalid dms declination with sepchar ' ': 'junk'
	"""
	dmsAngle = dmsAngle.strip()
	sign = 1
	if dmsAngle.startswith("+"):
		dmsAngle = dmsAngle[1:].strip()
	elif dmsAngle.startswith("-"):
		sign, dmsAngle = -1, dmsAngle[1:].strip()
	try:
		if sepChar=="":
			parts = dmsAngle[:2], dmsAngle[2:4], dmsAngle[4:]
		else:
			parts = dmsAngle.split(sepChar)
		if len(parts)==3:
			deg, min, sec = parts
		elif len(parts)==2:
			deg, min = parts
			sec = 0
		else:
			raise ValueError("Invalid # of parts")
		arcSecs = sign*(int(deg)*3600+float(min)*60+float(sec))
	except ValueError:
		raise LiteralParseError("Invalid dms declination with sepchar %s: %s"%(
			repr(sepChar), repr(dmsAngle)), None, dmsAngle)
	return arcSecs/3600


def fracHoursToDeg(fracHours):
	"""returns the time angle fracHours given in decimal hours in degrees.
	"""
	return float(fracHours)*360./24.


def degToHms(deg, sepChar=" ", secondFracs=3):
	"""converts a float angle in degrees to an time angle (hh:mm:ss.mmm).

	>>> degToHms(0)
	'00 00 00.000'
	>>> degToHms(122.056, secondFracs=1)
	'08 08 13.4'
	>>> degToHms(122.056, secondFracs=0)
	'08 08 13'
	>>> degToHms(-1.056, secondFracs=0)
	'-00 04 13'
	>>> degToHms(359.2222, secondFracs=4, sepChar=":")
	'23:56:53.3280'
	>>> "%.4f"%hmsToDeg(degToHms(256.25, secondFracs=9))
	'256.2500'
	"""
	sign = ""
	if deg<0:
		sign = "-"
		deg = -deg
	rest, hours = math.modf(deg/360.*24)
	rest, minutes = math.modf(rest*60)
	if secondFracs<1:
		secondFracs = -1
	return sign+sepChar.join(["%02d"%int(hours), "%02d"%abs(int(minutes)), 
		"%0*.*f"%(secondFracs+3, secondFracs, abs(rest*60))])


def degToDms(deg, sepChar=" ", secondFracs=2):
	"""converts a float angle in degrees to a sexagesimal string.
	>>> degToDms(0)
	'+0 00 00.00'
	>>> degToDms(-23.50, secondFracs=4)
	'-23 30 00.0000'
	>>> "%.4f"%dmsToDeg(degToDms(-25.6835, sepChar=":"), sepChar=":")
	'-25.6835'
	"""
	rest, degs = math.modf(deg)
	rest, minutes = math.modf(rest*60)
	if secondFracs==0:
		secondFracs = -1
	return sepChar.join(["%+d"%int(degs), "%02d"%abs(int(minutes)), 
		"%0*.*f"%(secondFracs+3, secondFracs, abs(rest*60))])


class NameMap(object):
	"""is a name mapper fed from a simple text file.

	The text file format simply is:

	<target-id> "TAB" <src-id>{whitespace <src-id>}

	src-ids have to be encoded quoted-printable when they contain whitespace
	or other "bad" characters ("="!).  You can have #-comments and empty
	lines.
	"""
	def __init__(self, src, missingOk=False):
		self._parseSrc(src, missingOk)
	
	def __contains__(self, name):
		return name in self.namesDict

	def _parseSrc(self, src, missingOk):
		self.namesDict = {}
		try:
			f = open(src)
		except IOError:
			if not missingOk:
				raise
			else:
				return
		try:
			for ln in f:
				if ln.startswith("#") or not ln.strip():
					continue
				ob, names = re.split("\t+", ln)
				for name in names.lower().split():
					self.namesDict[name.decode("quoted-printable")] = ob
		except ValueError:
			raise excs.LiteralParseError(
				"Syntax error in %s: Line %s not understood."%(src, repr(ln)),
				src, ln)
		f.close()
	
	def resolve(self, name):
		return self.namesDict[name.lower()]


def _test():
	import doctest, texttricks
	doctest.testmod(texttricks)


if __name__=="__main__":
	_test()
