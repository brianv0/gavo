#!/usr/bin/env python

"""
This script is the interface to importing resources into the VO.
"""

import sys
import os
from optparse import OptionParser

import pyparsing

import gavo
from gavo import textui
from gavo import config
from gavo import sqlsupport
from gavo import utils
from gavo import config
from gavo import parsing
from gavo.parsing import importparser
from gavo.parsing import resource


class Abort(Exception):
	pass


def process(opts, rd):
	res = resource.Resource(rd)
	res.importData(opts)
#	print res.dataSets[0].rows
	if opts.fakeonly:
		return
	res.export(opts.outputMethod)


def processAll(opts, args):
	for src in args:
		gavo.ui.displayMessage("Working on %s"%src)
		gavo.logger.info("Processing %s"%src)
		process(opts, importparser.getRd(os.path.join(os.getcwd(), src)))


def parseCmdline():
	parser = OptionParser(usage = "%prog [options] <rd-name>+")
	parser.add_option("-d", "--debug-productions", help="enable debugging for"
		" the given productions", dest="debugProductions", default="", 
		metavar="productions")
	parser.add_option("-n", "--fake-only", help="just parse, don't"
		" write anything (largely ignored with -w)", dest="fakeonly", 
		action="store_true")
	parser.add_option("-u", "--meta-only", help="just update meta data,"
		" don't parse source.", dest="metaOnly", action="store_true")
	parser.add_option("-m", "--max-rows", help="only import MAX_ROWS"
		" rows of every source", dest="maxRows", default=None,
		type="int", action="store")
	parser.add_option("-p", "--profile", help="use PROFILE to access db",
		dest="dbProfile", action="store", type="str", 
		default=config.get("parsing", "dbDefaultProfile"), metavar="PROFILE")
	parser.add_option("-v", "--verbose", help="talk a lot while working",
		dest="verbose", action="store_true")
	parser.add_option("-c", "--continue-bad", help="go on after a source had",
		" an error", dest="ignoreBadSources", action="store_true")
	parser.add_option("-o", "--output-method", help="output destination, one of"
		" sql, votable, none.  Default: sql",
		action="store", default="sql", dest="outputMethod")
	(opts, args) = parser.parse_args()
	opts.debugProductions = [s.strip() 
		for s in opts.debugProductions.split(",") if s.strip()]
	parsing.verbose = opts.verbose
	config.setDbProfile(opts.dbProfile)
	if not args:
		parser.print_help()
		sys.exit(1)
	return opts, args


def main():
	try:
		processAll(*parseCmdline())
	except Abort, msg:
		sys.exit(1)
	except SystemExit, msg:
		sys.exit(msg.code)
	except gavo.Error, msg:
		gavo.logger.error("Operation failed:", exc_info=True)
		sys.stderr.write("Error: %s\n(more information may be available"
			" in the log)"%msg)
	except Exception, msg:
		gavo.logger.error("Uncaught exception in gavoimp:", exc_info=True)
		sys.stderr.write("Uncaught exception (see log for details): %s\n"%(msg))
