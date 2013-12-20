all: lint pep8

lint:
	# Analyze code
	# don't show recommendations, info, comments, report
	# W0613 - unused argument
	# Ignore cherrypy class members as they are dynamically added
	pylint -d c,r,i,W0613 -r n -f colorized \
		   --notes= \
		   --ignored-classes=cherrypy \
		   ./ipsilon

pep8:
	# Check style consistency
	pep8 ipsilon