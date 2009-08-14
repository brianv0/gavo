# We *could* make this a namespace package, but right now cdbs support for
# them seems to be buggy, and it doesn't really buy us anything here.
# In the monolithic package, it doesn't anyway, and subpackages all depend
# on gavoutils anyway, so we put __init__.py there.
# 
#__import__('pkg_resources').declare_namespace(__name__)
