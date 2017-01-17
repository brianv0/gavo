"""
A little python script that changes/updates the copyright notices
in all python files in the distribution.

The copyright notices are identified by being comments opened
with #c at the start of a line before the first statement in a python
file.  The current copyright text is embedded in this file.

This file should be started in the directory containing the sources
and will traverse the subdirectories.
"""

#c Copyright 2008-2014, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import fnmatch
import os
import sys
import tokenize


CUR_TEXT = """#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.

"""


class NoComment(Exception):
	pass


def makeReadline(source):
	"""returns a function that, on each call, returns one more item from
	source.
	"""
	iterator = iter(source)

	def readline():
		try:
			return iterator.next()
		except StopIteration:
			return ""
	
	return readline


def findCopyrightComment(lineSource):
	"""returns the start end end indices of the comment block in 
	the readline-like thing lineSource.

	Trailing newlines are included.

	This raises a NoComment exception if the copyright comment is not
	found.
	"""
	tokens = tokenize.generate_tokens(lineSource)
	# find the first #c comment or give up if there's an instruction before
	for tok in tokens:
		if tok[0] not in set([tokenize.STRING, tokenize.NEWLINE, 
				tokenize.COMMENT, tokenize.NL]):
			raise NoComment("Instruction found")
		if tok[0]==tokenize.COMMENT and tok[1].startswith("#c"):
			break
	else:
		raise NoComment("EOF encountered")
	
	startLine = tok[2][0]-1
	# no need to check ranges as there's an ENDMARKER token at the end
	while (tok[0]==tokenize.NL or tok[0]==tokenize.NEWLINE
			or (
				tok[0]==tokenize.COMMENT and tok[1].startswith("#c"))):
		endLine = tok[3][0]-1
		tok  = tokens.next()
	return startLine, endLine
	

def processOne(fName):
	"""fixes the copyright comment in fName if it's there.

	The function raises a NoComment exception if fName has no copyright
	comment.
	"""
	with open(fName) as f:
		source = f.readlines()

	startLine, endLine = findCopyrightComment(makeReadline(source))
	
	# work on lines rather than tokens to preserve whitespace choices
	source[startLine:endLine] = [CUR_TEXT]
	with open(fName, "w") as f:
		f.write("".join(source))


def main():
	for dirpath, dirnames, filenames in os.walk("."):
		for filename in filenames:
			if fnmatch.fnmatch(filename, "*.py"):
				try:
					processOne(os.path.join(dirpath, filename))
				except NoComment:
					sys.stdout.write("Skipping %s\n"%os.path.join(dirpath, filename))


if __name__=="__main__":
	main()
