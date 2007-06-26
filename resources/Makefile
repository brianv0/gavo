GAVO_HOME ?= /var/gavo

install:
	rsync -av --exclude ".svn" --exclude ".*.swp" --exclude "/README"\
		--exclude "Makefile" . ${GAVO_HOME}
