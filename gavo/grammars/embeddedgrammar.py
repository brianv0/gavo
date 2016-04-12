"""
A grammars defined by code embedded in the RD.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import base
from gavo import rscdef
from gavo.grammars import common


class EmbeddedIterator(rscdef.ProcApp):
	"""A definition of an iterator of a grammar.

	The code defined here becomes the _iterRows method of a 
	grammar.common.RowIterator class.  This means that you can
	access self.grammar (the parent grammar; you can use this to transmit
	properties from the RD to your function) and self.sourceToken (whatever
	gets passed to parse()).
	"""
	name_ = "iterator"
	requiredType = "iterator"
	formalArgs = "self"


class EmbeddedPargetter(rscdef.ProcApp):
	"""A definition of the parameter getter of an embedded grammar.

	The code defined here becomes the getParameters method of the generated
	row iterator.  This means that the dictionary returned here becomes
	the input to a parmaker.

	If you don't define it, the parameter dict will be empty.

	Like the iterators, pargetters see the current source token as
	self.sourceToken, and the grammar as self.grammar.
	"""
	name_ = "pargetter"
	requiredType = "pargetter"
	formalArgs = "self"


class EmbeddedGrammar(common.Grammar, base.RestrictionMixin):
	"""A Grammar defined by a code application.

	To define this grammar, write a ProcApp iterator leading to code yielding
	row dictionaries.  The grammar input is available as self.sourceToken;
	for normal grammars within data elements, that would be a fully
	qualified file name.

	Grammars can also return one "parameter" dictionary per source (the
	input to a make's parmaker).  In an embedded grammar, you can define
	a pargetter to do that.  It works like the iterator, except that
	it returns a single dictionary rather than yielding several of them.

	This could look like this, when the grammar input is some iterable::

		<embeddedGrammar>
	  	<iterator>
	    	<setup>
	      	<code>
	        	testData = "a"*1024
	      	</code>
	    	</setup>
	    	<code>
	      	for i in self.sourceToken:
	        	yield {'index': i, 'data': testData}
	    	</code>
	  	</iterator>
		</embeddedGrammar>
	"""
	name_ = "embeddedGrammar"
	_iterator = base.StructAttribute("iterator", default=base.Undefined,
		childFactory=EmbeddedIterator,
		description="Code yielding row dictionaries", copyable=True)
	_pargetter = base.StructAttribute("pargetter", default=None,
		childFactory=EmbeddedPargetter,
		description="Code returning a parameter dictionary", copyable=True)
	_isDispatching = base.BooleanAttribute("isDispatching", default=False,
		description="Is this a dispatching grammar (i.e., does the row iterator"
		" return pairs of role, row rather than only rows)?", copyable=True)
	_notify = base.BooleanAttribute("notify", default=False,
		description="Enable notification of begin/end of processing (as"
			" for other grammars; embedded grammars often have odd source"
			" tokens for which you don't want that).", copyable=True)
	
	def onElementComplete(self):
		self._onElementCompleteNext(EmbeddedGrammar)
		class RowIterator(common.RowIterator):
			_iterRows = self.iterator.compile()
			notify = self.notify

		if self.pargetter:
			RowIterator.getParameters = self.pargetter.compile()

		self.rowIterator = RowIterator
