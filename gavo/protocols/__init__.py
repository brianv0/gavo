"""
IVOA, W3C, and custom protocol helpers (in cooperation with twisted-based
code in weg).

Some of these modules will register mixins.  To do this, they need
gavo.rscdesc imported.  Since other protocols may want to run without
the need for RDs, we don't import anything depending on RDs here.

Both commandline.py and standalone.tac import gavo.protocols.basic to get a
common set of "standard" protocols/mixins defined.

The guiding line should be: Stuff that depends on nevow (or even twisted)
should go to web or svcs, generic code should be here.  Of course, these
rules are constantly bent.
"""
