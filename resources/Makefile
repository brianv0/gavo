GAVO_HOME ?= /var/gavo

install:
	rsync -av --exclude ".svn" --exclude ".*.swp" --exclude "/README"\
		--exclude "/Makefile" --exclude "/inputs" . ${GAVO_HOME}
