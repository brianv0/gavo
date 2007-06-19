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
	if opts.outputMethod=="sql":
		res.exportToSql()
	res.rebuildDependents()


def processAll(opts, args):
	for src in args:
		gavo.ui.displayMessage("Working on %s"%src)
		gavo.logger.info("Processing %s"%src)
		process(opts, importparser.getRd(src))


def parseCmdline():
	parser = OptionParser(usage = "%prog [options] <rd-name>+")
	parser.add_option("-p", "--debug-productions", help="enable debugging for"
		" the given productions", dest="debugProductions", default="", 
		metavar="productions")
	parser.add_option("-n", "--fake-only", help="don't talk to the db engine,"
		" only spit out raw SQL", dest="fakeonly", action="store_true")
	parser.add_option("-m", "--max-rows", help="only import MAX_ROWS"
		" rows of every source", dest="maxRows", default=None,
		type="int", action="store")
	parser.add_option("-v", "--verbose", help="talk a lot while working",
		dest="verbose", action="store_true")
	parser.add_option("-o", "--output-method", help="output destination, one of"
		" sql, plain, votable, none.  Default: sql (XXX not implemented XXX)",
		action="store", default="sql", dest="outputMethod")
	(opts, args) = parser.parse_args()
	opts.debugProductions = [s.strip() 
		for s in opts.debugProductions.split(",") if s.strip()]
	parsing.verbose = opts.verbose
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
	except Exception, msg:
		gavo.logger.error("Uncaught exception in gavoimp:", exc_info=True)
		utils.fatalError("Uncaught exception (see log for details): %s"%(msg))
