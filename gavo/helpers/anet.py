"""
Code to obtain WCS headers for fits files using astrometry.net
"""

from cStringIO import StringIO
import os
import shutil
import subprocess

from gavo import base
from gavo.utils import fitstools
from gavo.utils import codetricks
from gavo.utils import pyfits

anetPath = "/usr/local/astrometry/bin"
anetIndexPath = "/usr/local/astrometry/data"
solverBin = os.path.join(anetPath, "solve-field")
tabsortBin = os.path.join(anetPath, "tabsort")
getHealpixBin = os.path.join(anetPath, "get-healpix")
image2xyBin = os.path.join(anetPath, "image2xy")
blindBin = "%s"%os.path.join(anetPath, "blind")
sextractorBin = "sextractor"

# pass this (or your adaptation of this) as sexScript to getWCSFieldsFor to 
# have sextractor do the source extraction
anetSex = """# sextractor control file to make it play with astrometry.net
CATALOG_TYPE     FITS_1.0
# this is the output filename:
CATALOG_NAME     out.xyls
PARAMETERS_NAME  xylist.param
VERBOSE_TYPE     QUIET
"""

# export column spec for sextractor
sexParam = """X_IMAGE
Y_IMAGE
MAG_ISO
ELONGATION
"""


class Error(base.Error):
	pass

class NotSolved(Error):
	pass

class ObjectNotFound(Error):
	pass

class ShellCommandFailed(Error):
	def __init__(self, msg, retcode):
		Error.__init__(self, msg)
		self.msg, self.retcode = msg, retcode
	
	def __str__(self):
		return "External program failure (%s).  Program output: %s"%(
			self.retcode, self.msg)


# Template for control file for blind.
controlTemplate="""sdepth %(startob)s
depth %(endob)s
fieldunits_lower %(lower_pix)s
fieldunits_upper %(upper_pix)s
%(fieldsize)s
quadsize_min 80
%(index_statements)s
fields %(fields)s
parity 2
verify_pix 1
tol 0.01
distractors 0.25
ratio_toprint 100
tweak off
tweak_aborder 3
tweak_abporder 3
tweak_skipshift
field out.fits
solved out.solved
match out.match.fits
indexrdls out.rd.fits
wcs out.wcs
log out.log
cancel out.cancel
xcol %(xcol)s
ycol %(ycol)s
total_timelimit %(total_timelimit)s
total_cpulimit %(total_cpulimit)s
run
"""


def _feedFile(targDir, fName, sexScript=anetSex, **ignored):
	"""links fName to "in.fits" in the sandbox.

	It also writes a config file anet.sex for sextractor.
	"""
	os.symlink(os.path.join(os.getcwd(), fName), 
		os.path.join(targDir, "in.fits"))
	if sexScript:
		f = open(os.path.join(targDir,"anet.sex"), "w")
		f.write(sexScript)
		f.close()
	f = open(os.path.join(targDir, "xylist.param"), "w")
	f.write(sexParam)
	f.close()


def _runShellCommand(cmd, args):
	cmdline = "%s %s"%(cmd, args)
	proc = subprocess.Popen(cmdline, shell=True, stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT)
	msg = proc.communicate()[0]
	if proc.returncode==-2:
		raise KeyboardInterrupt("Child was siginted")
	elif proc.returncode:
		raise ShellCommandFailed(msg, proc.returncode)


def _extractSex(filterFunc=None):
	"""does source extraction using Sextractor.

	If filterFunc is not None, it is called before sorting the extracted
	objects. It must change the file named in the argument in place.
	"""
	_runShellCommand(sextractorBin, "-c anet.sex -FILTER N in.fits")
	if filterFunc is not None:
		filterFunc("out.xyls")
	_runShellCommand(tabsortBin, "MAG_ISO out.xyls out.fits")


def _extractAnet(filterFunc=None):
	"""does source extraction using astrometry.net's source extractor.

	If filterFunc is not None, it is called before sorting the extracted
	objects. It must change the file named in the argument in place.
	"""
	_runShellCommand(image2xyBin, "in.fits")
	if filterFunc is not None:
		filterFunc("in.xy.fits")
	_runShellCommand(tabsortBin, "FLUX in.xy.fits out.fits -d")


def _resolve(fName, solverParameters={}, sexScript=None, objectFilter=None,
		copyTo=None):
	"""runs the astrometric calibration pipeline.

	solverParameters maps any of the keys defined in controlTemplate
	to desired values; some defaults are provided in the function.

	This function litters the working directory with all kinds of files and does
	not clean up, so you'd better run it in a sandbox.

	It raises a NotSolved exception if no solution could be found; otherwise
	you should find the solution in out.wcs (or whatever you gave for wcs).
	"""
	paramDefaults = {
		"index_statements": "index %s/index-218.fits"%anetIndexPath,
		"total_timelimit": 600,
		"total_cpulimit": 600,
		"fields": "1",
		"startob": "0",
		"endob": "200",
		"lower_pix": 0.2,
		"upper_pix": 0.3,
		"fieldsize": "",
		"xcol": "X",
		"ycol": "Y",
	}
	if sexScript:
		_extractSex(objectFilter)
		paramDefaults["xcol"], paramDefaults["ycol"] = "X_IMAGE", "Y_IMAGE"
	else:
		_extractAnet(objectFilter)
	paramDefaults.update(solverParameters)
	minInd, maxInd = int(paramDefaults["startob"]), int(
		paramDefaults["endob"])
	controlFragments = []
	for startInd, endInd in zip(range(minInd, maxInd-10, 5),
			range(minInd+10, maxInd, 5)):
		paramDefaults["startob"], paramDefaults["endob"] = startInd, endInd
		controlFragments.append(controlTemplate%paramDefaults)
	f = open("blind.control", "w")
	f.write("\n\n".join(controlFragments))
	f.close()
	f = os.popen(blindBin, "w")
	f.write("\n\n".join(controlFragments))
	f.flush()
	status = f.close()
	if copyTo is not None:
		try:
			shutil.rmtree(copyTo)
		except os.error:
			pass
		shutil.copytree(".", copyTo)
	if os.path.exists("out.solved"):
		return
	raise NotSolved(fName)


def _retrieveWCS(srcDir, fName, **ignored):
	return pyfits.getheader("out.wcs").ascard


def _makeFieldsize(fName):
	"""makes fieldw and fieldh statements for blind control files from the primary
	header of a FITS file.
	"""
	f = open(fName)
	header = fitstools.readPrimaryHeaderQuick(f)
	f.close()
	return "fieldw %d\nfieldh %d"%(header["NAXIS1"], header["NAXIS2"])


def getWCSFieldsFor(fName, solverParameters, sexScript=None, objectFilter=None,
		copyTo=None):
	"""returns a pyfits cardlist for the WCS fields on fName.

	solverParameters is a dictionary mapping solver keys to their values,
	sexScript is a script for SExtractor, and its presence means that
	SExtractor should be used for source extraction rather than what anet
	has built in.  objectFilter is a function that is called with the
	name of the FITS with the extracted sources.  It can remove or add
	sources to that file before astrometry.net tries to match.

	To see what solverParameters  are avaliable, check the controlTemplate
	above; additionally, you can give an indices key; enumerate the index
	files you want to use with names relative to anet.anetIndexPath, and
	the appropriate index_statements will be generated for you.  indices
	override any index_statements keys.
	"""
	if not "fieldsize" in solverParameters:
		solverParameters["fieldsize"] = _makeFieldsize(fName)
	if "indices" in solverParameters:
		solverParameters["index_statements"] = "\n".join("index %s"%
			os.path.join(anetIndexPath, n) for n in solverParameters["indices"])
	try:
		res = codetricks.runInSandbox(_feedFile, _resolve, _retrieveWCS,
			fName, solverParameters=solverParameters, sexScript=sexScript,
			objectFilter=objectFilter, copyTo=copyTo)
	except NotSolved:
		return None
	return res

