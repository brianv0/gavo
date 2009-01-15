"""
Code defining much of our IVOA interface.

Many of these modules will register mixins.  To do this, they need
gavo.rscdesc imported.  Since other protocols may want to run without
the need for RDs, we don't import anything depending on RDs here.

Both commandline.py and standalone.tac import gavo.protocols.basic to get a
common set of "standard" protocols/mixins defined.
"""

from gavo.protocols import servicelist
