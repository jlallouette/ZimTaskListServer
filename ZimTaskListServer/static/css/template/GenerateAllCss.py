# ----------------------------------------------------------------------------
# ZimTaskListServer: Management and centralization of tasks in Zim notebooks.
# Copyright (c) 2016-2017 Jules Lallouette
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# ----------------------------------------------------------------------------
import os
import sys
import shutil

if len(sys.argv) > 2:
	path = sys.argv[1]
	if not path.endswith('/'):
		path += '/'
	cssTemplatePath = sys.argv[2]

	for valFile in os.listdir(path):
		if valFile.endswith('.conf'):
			cssName = valFile.replace('.conf', '.css')
			with open(path + cssName, 'w') as newfile:
				with open(cssTemplatePath, 'r') as template:
					for tempLine in template:
						finalLine = tempLine
						with open(valFile, 'r') as valContent:
							for line in valContent:
								vals = line.split(':')
								finalLine = finalLine.replace(vals[0].strip(' \n'), vals[1].strip(' \n'))
						newfile.write(finalLine)
			shutil.move(path + cssName, path + '../' + cssName)
else:
	print('Needs to be launched with 2 arguments !')

