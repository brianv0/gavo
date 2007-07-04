#!/bin/sh
# converts a resource descriptor to html ("doc") and puts the HTML
# to $GAVO_HOME/rddocs
# You need xsltproc for this to work.

execDir=`dirname $0`
stylesheet=$execDir/../docs/rd.xslt
export GAVO_HOME=${GAVO_HOME:-/var/gavo}
targetDir=$GAVO_HOME/rddocs
mkdir -p $targetDir

while [ ! -z "$1" ]
do
	xsltproc "$stylesheet" "$1" > $targetDir/`basename ${1%.vord}`.html
	shift
done

