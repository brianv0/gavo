"""
Code to obtain WCS headers for fits files using astrometry.net
"""

# Within ARI, this only runs on saiph
# XXX -- make this more configurable -- anetPath, anetIndexPath in config?

import os

import pyfits

import gavo
from gavo import fitstools
from gavo import utils

anetPath = "/data/anet/astrometry/bin"
anetIndexPath = "/data/anet/astrometry/data"
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


class Error(gavo.Error):
	pass

class NotSolved(Error):
	pass

class ObjectNotFound(Error):
	pass

class ShellCommandFailed(Error):
	pass


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
ratio_toprint 1000
ratio_tokeep 1e+09
ratio_tosolve 1e+09
ratio_tobail 1e-100
tweak on
tweak_aborder 3
tweak_abporder 3
tweak_skipshift
field out.fits
solved out.solved
match out.match.fits
indexrdls out.rd.fits
indexrdls_solvedonly
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
	f = open(os.path.join(targDir,"anet.sex"), "w")
	f.write(sexScript)
	f.close()
	f = open(os.path.join(targDir, "xylist.param"), "w")
	f.write(sexParam)
	f.close()


def _runShellCommand(cmd, args, quiet=False):
	cmdline = "%s %s"%(cmd, args)
	if quiet:
		cmdline += " 2>&1 >/dev/null"
	if os.system(cmdline):
		raise ShellCommandFailed()


def _extractSex(filterFunc=None):
	"""does source extraction using Sextractor.

	If filterFunc is not None, it is called before sorting the extracted
	objects. It must change the file named in the argument in place.
	"""
	_runShellCommand(sextractorBin, "-c anet.sex -FILTER N in.fits", quiet=True)
	if filterFunc is not None:
		filterFunc("out.xyls")
	_runShellCommand(tabsortBin, "-i out.xyls -o out.fits -c MAG_ISO",
		quiet=True)


def _extractAnet(filterFunc=None):
	"""does source extraction using astrometry.net's source extractor.

	If filterFunc is not None, it is called before sorting the extracted
	objects. It must change the file named in the argument in place.
	"""
	_runShellCommand(image2xyBin, "in.fits")
	if filterFunc is not None:
		filterFunc("in.xy.fits")
	_runShellCommand(tabsortBin, "-i in.xy.fits -o out.fits -c FLUX -d")


def _resolve(fName, solverParameters={}, sexScript=None, objectFilter=None):
	"""runs the astrometric calibration pipeline.

	solverParameters maps any of the keys defined in controlTemplate
	to desired values; some defaults are provided in the function.

	This function litters the working directory with all kinds of files and does
	not clean up, so you'd better run it in a sandbox.

	It raises a NotSolved exception if no solution could be found; otherwise
	you should find the solution in out.wcs (or whatever you gave for wcs).
	"""
	paramDefaults = {
		"index_statements": "index %s/index-218"%anetIndexPath,
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
	f = os.popen(blindBin, "w")
	f.write("\n\n".join(controlFragments))
	f.flush()
	status = f.close()
#	open("/home/msdemlei/control", "w").write("\n\n".join(controlFragments))
#	open("/home/msdemlei/last.log", "w").write(open("out.log").read())
#	open("/home/msdemlei/out.xyls", "w").write(open("out.xyls").read())
#	open("/home/msdemlei/out.fits", "w").write(open("out.fits").read())
	if os.path.exists("out.solved"):
		return
	raise NotSolved(fName)


def _retrieveWcs(srcDir, fName, **ignored):
	return pyfits.getheader("out.wcs").ascard


def _makeFieldsize(fName):
	"""makes fieldw and fieldh statements for blind control files from the primary
	header of a FITS file.
	"""
	f = open(fName)
	header = fitstools.readPrimaryHeaderQuick(f)
	f.close()
	return "fieldw %d\nfieldh %d"%(header["NAXIS1"], header["NAXIS2"])


def getWCSFieldsFor(fName, solverParameters, sexScript=None, objectFilter=None):
	"""returns a pyfits cardlist for the WCS fields on fName.
	"""
	if not "fieldsize" in solverParameters:
		solverParameters["fieldsize"] = _makeFieldsize(fName)
	try:
		res = utils.runInSandbox(_feedFile, _resolve, _retrieveWcs, fName,
			solverParameters=solverParameters, sexScript=sexScript,
			objectFilter=objectFilter)
	except NotSolved:
		return None
	return res

