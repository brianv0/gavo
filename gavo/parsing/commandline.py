#!/usr/bin/env python

"""
This script is the interface to importing resources into the VO.
"""

import sys
import os
import traceback
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


def process(opts, args):
	src, ddIds = args[0], args[1:]
	try:
		rd = importparser.getRd(os.path.join(os.getcwd(), src), forImport=True)
	except gavo.RdNotFound:
		rd = importparser.getRd(src, forImport=True)
	if opts.createShared:
		rd.prepareForSystemImport()
	if opts.metaOnly:
		rd.importMeta(set(ddIds))
	else:
		res = resource.Resource(rd)
		res.importData(opts, set(ddIds))
		res.export(opts.outputMethod, set(ddIds))


def parseCmdline():
	parser = OptionParser(usage = "%prog [options] <rd-name> {<data-id>}")
	parser.add_option("-d", "--debug-productions", help="enable debugging for"
		" the given productions", dest="debugProductions", default="", 
		metavar="productions")
	parser.add_option("-u", "--meta-only", help="just update table meta"
		" (privileges, column descriptions,...).", dest="metaOnly", 
		action="store_true")
	parser.add_option("-m", "--max-rows", help="only import MAX_ROWS"
		" rows of every source", dest="maxRows", default=None,
		type="int", action="store")
	parser.add_option("-p", "--profile", help="use PROFILE to access db",
		dest="dbProfile", action="store", type="str", 
		default=config.get("parsing", "dbDefaultProfile"), metavar="PROFILE")
	parser.add_option("-s", "--system", help="create shared tables",
		dest="createShared", action="store_true")
	parser.add_option("-v", "--verbose", help="talk a lot while working",
		dest="verbose", action="store_true")
	parser.add_option("-c", "--continue-bad", help="go on after a source had"
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
		process(*parseCmdline())
	except Abort, msg:
		sys.exit(1)
	except SystemExit, msg:
		sys.exit(msg.code)
	except Exception, msg:
		utils.displayError(msg)
