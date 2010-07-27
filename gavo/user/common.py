"""
Common functionality for the DC user interface.

This module contains, in partiular, the interface for having "easy subcommands"
using argparse.  The idea is to use the exposedFunction decorator on functions
that should be callable from the command line as subcommands; the functions
only take a single argument, the stuff returned from argparse.  Then, say
in the module containing them,

	args = _makeParser(globals()).parse_args()
	args.subAction(args)

To specify the command line arguments to the function, use Args.  See
admin.py for an example.
"""


from gavo.imp import argparse


class Arg(object):
	"""an argument/option to a subcommand.

	These are constructed with positional and keyword parameters to
	the argparse's add_argument.
	"""
	def __init__(self, *args, **kwargs):
		self.args, self.kwargs = args, kwargs
	
	def add(self, parser):
		parser.add_argument(*self.args, **self.kwargs)


def exposedFunction(argSpecs=(), help=None):
	"""a decorator exposing a function to parseArgs.

	argSpecs is a sequence of Arg objects.  This defines the command line
	interface to the function.

	The decorated function itself must accept a single argument,
	the args object returned by argparse's parse_args.
	"""
	def deco(func):
		func.subparseArgs = argSpecs
		func.subparseHelp = help
		return func
	return deco


def makeParser(functions):
	"""returns a command line parser parsing subcommands from functions.

	functions is a dictionary (as returned from globals()).  Subcommands
	will be generated from all objects that have a subparseArgs attribute;
	furnish them using the commandWithArgs decorator.

	This attribute must contain a sequence of Arg items (see above).
	"""
	parser = argparse.ArgumentParser()
	subparsers = parser.add_subparsers()
	for name, val in functions.iteritems():
		args = getattr(val, "subparseArgs", None)
		if args is not None:
			subForName = subparsers.add_parser(name, help=val.subparseHelp)
			for arg in args:
				arg.add(subForName)
			subForName.set_defaults(subAction=val)
	return parser
