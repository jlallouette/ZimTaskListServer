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
from flask import session
from TaskToDB import *

class PageManager:

	def PrintChckBoxOptions(self):
		html = '<option ' + ('selected' if session['chckboxState'] == 0 else '') + ' value="0">All</option>'
		html += '<option ' + ('selected' if session['chckboxState'] == 1 else '') + ' value="1">Todo</option>'
		html += '<option ' + ('selected' if session['chckboxState'] == 2 else '') + ' value="2">Done</option>'
		html += '<option ' + ('selected' if session['chckboxState'] == 3 else '') + ' value="3">Canceled</option>'
		return  Markup(html)

	def PrintOrderBy(self):
		def PrintOrderByDropDown(name, content):
			html = '<select name="' + name + '" id="' + name + '" onchange="this.form.submit()">'
			html += '<option ' + ('selected' if content == 'none' else '') + ' value="none">None</option>'
			options = [('priority', 'Priority'), ('duedate', 'Due Date'), ('duration', 'Duration')]
			nbopt = 0
			for opt in options:
				if content == opt[0] or not opt[0] in session['orderbyList']:
					html += '<option ' + ('selected' if content == opt[0] else '') + ' value="' + opt[0] + '">' + opt[1] + '</option>'
					nbopt += 1
			html += '</select>'
			if nbopt > 0:
				return html
			else:
				return ''
		html = ''
		# cleanup list
		fullyread = False
		while not fullyread:
			for i in range(0, len(session['orderbyList'])):
				fullyread = True
				if (session['orderbyList'][i] == 'none') and (i < len(session['orderbyList']) - 1):
					del session['orderbyList'][i]
					fullyread = False
					break
		if session['orderbyList'][-1] != 'none':
			session['orderbyList'].append('none')
		# display
		for i in range(0, len(session['orderbyList'])):
			html += PrintOrderByDropDown('orderby'+str(i), session['orderbyList'][i])
		return Markup(html)

	def HasOrderByClauses(self):
		return len(session['orderbyList']) > 1

	def GroupByTaskGroups(self):
		return session['groupbyState'] == 'taskgroup'

	def UpdateTagFilter(self):
		# cleanup list
		fullyread = False
		while not fullyread:
			for i in range(0, len(session['tagfilterlist'])):
				fullyread = True
				if (session['tagfilterlist'][i] == '-') and (i < len(session['tagfilterlist']) - 1):
					del session['tagfilterlist'][i]
					fullyread = False
					break
		if session['tagfilterlist'][-1] != '-':
			session['tagfilterlist'].append('-')

	def PrintTagFilter(self):
		html = ''
		self.UpdateTagFilter()
		# display
		for i in range(0, len(session['tagfilterlist'])):
			if session['tagfilterlist'][i] != u'-':
				html += u'<button class="TagButton" type="submit" value="-" id="tagfilter' + unicode(i) + u'" name="tagfilter' + unicode(i) + u'">' + session['tagfilterlist'][i] + u'</button>'
		return Markup(html)

	def HasTagFilters(self):
		return len(session['tagfilterlist']) > 1

	def CheckRegExp(self):
		# check that the regexp is valid
		try:
			p = re.compile(session['searchFilt'])
			# transform it to match both low and upper case
			tmpExp = ''
			inside = 0
			escape = False
			for car in session['searchFilt']:
				if (car == '\\'):
					escape = True
					tmpExp += car
					continue
				elif ((car == '(') or (car == '[')) and not escape:
					inside += 1
					tmpExp += car
				elif (car == ')' or car == ']') and not escape:
					inside -= 1
					tmpExp += car
				elif inside == 0 and ((car >= 'a' and car <= 'z') or (car >= 'A' and car <= 'Z')):
					tmpExp += '[' + car.lower() + car.upper() + ']'
				else:
					tmpExp += car
				escape = False
			session['searchFilt'] = tmpExp
			# check that the regexp doesn't match an empty string
			p = re.compile(session['searchFilt'])
			if p.match('') and session['searchFilt'] != '':
				session['searchFilt'] = 'Invalid, can match empty strings'
		except re.error:
			session['searchFilt'] = 'Invalid regexp'

	def GetQuerry(self):
		if session['groupbyState'] == 'taskgroup':
			cond = True
			# Tag filtering
			if session['tagfilterlist'] != ['-']:
				tmpCond = False
				for tag in session['tagfilterlist']:
					if tag != '-':
						tmpCond = tmpCond | (Tag.name == tag)
				cond = cond & (tmpCond)
			# user filtering
			cond = cond & (NoteBook.user == User.get(User.login == session['login']))

			querry = TaskGroup.select().join(Task).join(TaskTags, JOIN.LEFT_OUTER).join(Tag, JOIN.LEFT_OUTER).join(NotePage, on = (NotePage.id == Task.parentPage)).join(NoteBook)

			# ordering
			orderlist = []
			taskJoined = False
			for order in session['orderbyList']:
				if order == 'priority':
					if not taskJoined:
						querry = querry.group_by(TaskGroup)
						taskJoined = True
					orderlist.append(fn.Max(Task.priority).desc())
				elif order == 'duedate':
					if not taskJoined:
						taskJoined = True
					querry = querry.join(TaskDates, JOIN.LEFT_OUTER, on = (Task.id == TaskDates.from_task)).join(DueDate, JOIN.LEFT_OUTER).group_by(TaskGroup)
					orderlist.append((datetime.today() - fn.Min(DueDate.date)).desc())
				elif order == 'duration':
					if not taskJoined:
						querry = querry.group_by(TaskGroup)
						taskJoined = True
					orderlist.append((10 - fn.SUM(Task.duration)).desc())
			orderlist.append(TaskGroup.name)

			querry = querry.where(cond).order_by(*orderlist).distinct()
			# state filtering
			if session['chckboxState'] > 0:
				querry = [taskgroup for taskgroup in querry if taskgroup.getState() == session['chckboxState'] - 1]
			# search bar filtering
			if len(session['searchFilt']) > 0:
				p = re.compile(session['searchFilt'])
				querry = [taskgroup for taskgroup in querry if taskgroup.containsRegExp(p)]
		else:
			querry = Task.select().join(TaskTags, JOIN.LEFT_OUTER).join(Tag, JOIN.LEFT_OUTER).join(NotePage, on = (NotePage.id == Task.parentPage)).join(NoteBook)
			querry = querry.where(NoteBook.user == User.get(User.login == session['login']))
			# Tag filtering
			if session['tagfilterlist'] != ['-']:
				cond = False
				for tag in session['tagfilterlist']:
					if tag != '-':
						cond = cond | (Tag.name == tag)
				querry = querry.where(cond)
			if session['chckboxState'] == 0:
				querry = querry.where(Task.parent >> None)
			else:
				querry = querry.where((Task.state == session['chckboxState'] - 1) & (Task.parent >> None))
			# ordering
			orderlist = []
			for order in session['orderbyList']:
				if order == 'priority':
					orderlist.append(Task.priority.desc())
				elif order == 'duedate':
					querry = querry.join(TaskDates, JOIN.LEFT_OUTER, on=(TaskDates.from_task == Task.id)).join(DueDate, JOIN.LEFT_OUTER).group_by(Task)
					orderlist.append((datetime.today() - DueDate.date).desc())
				elif order == 'duration':
					orderlist.append((10 - Task.duration).desc())
			orderlist.append(Task.lineId)
			querry = querry.order_by(*orderlist)
			querry = querry.distinct()

			# Search bar filtering
			if len(session['searchFilt']) > 0:
				p = re.compile(session['searchFilt'])
				querry = [task for task in querry if task.containsRegExp(p)]

		return querry

	def TaskGroupQuery(self, tg):
		querry = Task.select().where(Task.group == tg)
		if session['chckboxState'] == 0:
			querry = querry.where(Task.parent >> None)
		else:
			querry = querry.where((Task.state == session['chckboxState'] - 1) & (Task.parent >> None))
		return querry.order_by(Task.lineId)

	def GetSubTaskFilter(self):
		if session['chckboxState'] == 0:
			return True
		else:
			return (Task.state == session['chckboxState'] - 1)

	def GetSubTaskOrdering(self):
		return (Task.lineId)

	def ParseAndHighlight(self, html):
		newhtml = unicode(html)
		if (session['searchFilt'] != ''):
			p = re.compile('^((?:(?:<[^<>]+>)|(?:[^<]))*?(' + session['searchFilt'] + '))')
			matching = True
			currInd = 0
			while matching:
				m = p.match(newhtml[currInd:])
				if m:
					replace = '<span class="searchhighlight">' + m.group(2) + '</span>'
					newhtml = newhtml[0:currInd+m.start(2)] + replace + newhtml[currInd+m.end(2):]
					currInd += m.end(2) + len(replace) - len(m.group(2))
				else:
					matching = False
		return Markup(newhtml)

	def GetSpecificScripts(self):
		val = session['prevOp']
		script = ''
		try:
			if 'AddTask' in val:
				idVal = val[7:]
				elemId = '#AddTask' + idVal
				script += '$(\'' + elemId + '\').slideToggle("fast");\n'
				script += 'goToByScroll(\''+ elemId + '\');\n'
				script += '$(\'#norm_' + idVal + '.AddTaskText\').focus();\n'
		except:
			pass
		return Markup(script)

