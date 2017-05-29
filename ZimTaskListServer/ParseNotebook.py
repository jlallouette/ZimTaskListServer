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
from sets import Set
import re
import datetime
import subprocess
from os import remove, close, chmod, walk
from tempfile import mkstemp
from Parameters import *
from Lock import *

class Task():
	def __init__(self, fileLink, indent, params, subtasks, groupId, lastModif, fullLine, parent = None, lineId = None):
		self.indent = indent
		self.params = params
		self.fullLine = fullLine

		self.fileLink = fileLink
		self.subtasks = subtasks
		self.groupId = groupId
		self.parent = parent
		self.lineId = lineId
		self.previousTask = None
		self.tags = Set()
		self.lastModif = lastModif
		self.due = []
		self.prio = 0
		self.descr = ''
		self.status = ''
		self.started = 0
		self.duration = 0
		self.comments = []

	def getIndentLevel(self):
		if (self.parent is None) :
			return 0
		else :
			return self.parent.getIndentLevel() + 1

	def applyTag(self, tag):
		if not tag in [_tag.lower() for _tag in self.tags]:
			self.tags.add(tag)
		for task in self.subtasks:
			task.applyTag(tag)

	def applyDueDate(self, dd):
		if not dd in self.due:
			self.due.append(dd)
		for task in self.subtasks:
			task.applyDueDate(dd)

	def parseAll(self):
		self.parseTags()
		self.parseDueDates()
		self.parseDuration()
		self.parsePrio()
		self.parseStatus()
		self.parseStarted()
		self.parseNext()
		self.parseComments()
		self.parseDescr()

	def parseTags(self):
		p = re.compile(u' @[a-z|A-Z|0-9]+')
		tags = p.findall(self.params)
		for tag in tags:
			self.applyTag(tag[1:])
		for task in self.subtasks:
			task.parseTags()

	def parseDueDates(self, parentDates = []):
		p = re.compile(u'\[d: ([0-9]+[-/][0-9]+[-/][0-9]+)( *)(c[0-9|dmy]+)?\]')
		p2 = re.compile(u'([0-9]+[ymd]?)')
		dates = p.findall(self.params)
		for date in dates:
			cyclic = (0, 0, 0)
			if len(date[2]) > 0:
				durations = p2.findall(date[2])
				cyclic = [0, 0, 0] # (years, months, days)
				for dur in durations:
					if dur[-1] == u'y':
						cyclic[0] += int(dur[0:-1])
					elif dur[-1] == u'm':
						cyclic[1] += int(dur[0:-1])
					else:
						cyclic[2] += int(dur[0:-1])
						
			self.due.append((datetime.datetime.strptime(date[0], '%Y-%m-%d').date(), cyclic, False))
			self.params = self.params.replace(u'[d: ' + date[0] + date[1] + date[2] + u']', u'')
		for pDate in parentDates:
			if pDate not in self.due:
				self.due.append((pDate[0], pDate[1], True))
		for task in self.subtasks:
			task.parseDueDates(self.due)

	def parseDuration(self):
		p = re.compile(u'\[t: ([0-9]*d)?([0-9]*h)?([0-9]*m)?([0-9]*s)?\]')
		durations = p.findall(self.params)
		self.duration = 0
		mults = [24*60*60, 60*60, 60, 1]
		for duration in durations:
			for i in range(0, 4):
				if len(duration[i]) > 0:
					self.duration += int(duration[i][0:-1]) * mults[i]
			self.params = self.params.replace(u'[t: ' + duration[0] + duration[1] + duration[2] + duration[3] + u']', u'')
		if self.duration == 0:
			self.duration = None
		tmp = 0
		for task in self.subtasks:
			task.parseDuration()
			if task.duration:
				tmp += task.duration
		if self.duration < tmp and tmp > 0:
			self.duration = tmp

	def parsePrio(self):
		self.prio = 0
		p = re.compile(u' !+ ?')
		prios = p.findall(self.params)
		for prio in prios:
			self.params = self.params.replace(prio, u' ')
			self.prio += len(prio) - 1
		for task in self.subtasks:
			task.parsePrio()

	def parseStatus(self):
		if (self.params.startswith(u'[')):
			self.status = self.params[1]
			self.params = self.params[4:]
		else:
			self.status = 's'
		for task in self.subtasks:
			task.parseStatus()

	def parseStarted(self):
		p = re.compile(u'^Started: ')
		m = p.match(self.params)
		if m:
			self.started = 1
			self.params = self.params[m.end():]
		for task in self.subtasks:
			task.parseStarted()

	def parseNext(self):
		p = re.compile(u'Next: ')
		m = p.match(self.params)
		if m:
			if (self.parent):
				if self.parent == -1:
					self.previousTask = -1
				else:
					ind = self.parent.GetSubTaskInd(self)
					if (ind > 0):
						self.previousTask = self.parent.subtasks[ind]
			self.params = self.params[0:m.start()] + self.params[m.end():]
		for task in self.subtasks:
			task.parseNext()

	def parseComments(self):
		p = re.compile(u'\[comment: \[[0-9]+[-/][0-9]+[-/][0-9]+\]>(?:[^\[\]]*(?:\[\[.*?\]\])*)*?\]')
		comments = p.findall(self.params)
		for com in comments:
			self.comments.append(com[1:-1])
			self.params = self.params.replace(com, u"")
		for task in self.subtasks:
			task.parseComments()
		
	def parseDescr(self):
		self.descr = self.params
		for task in self.subtasks:
			task.parseDescr()

		
	def GetSubTaskInd(self, _task):
		for i in range(0, len(self.subtasks)):
			if (self.subtasks[i] == _task):
				return i
		return -1

	def getMaxPrio(self):
		mp = self.prio
		for tsk in self.subtasks:
			mp = max(mp, tsk.getMaxPrio())
		return mp

	# Print a task on screen
	def printToConsole(self):
		tmp = str(self.groupId) + self.status + '|' 
		if self.previousTask:
			tmp += '>'
		else:
			tmp += ' '
		tmp += '\t' * self.getIndentLevel() + self.descr;
		tmp +=  ' '  + self.fileLink
		for tag in self.tags:
			tmp += ', ' + tag
		tmp += ' // '
		for date in self.due:
			tmp += str(date[0]) + ' c' + str(date[1]) + ' '
		tmp += str(self.prio)
		print(tmp.encode('utf-8'))
		for com in self.comments:
			print(com.encode('utf-8'))
		for subTask in self.subtasks :
			subTask.printToConsole()


class TaskParser:
	rootTask = None
	pages = {}

	# Parse the file
	def ParseFile(self, NotePath, dbNotepgFct):
		self.allPages = []

		# Parse a task from a text line
		def ParseTask(line, pageLink, groupId, lastModif, _lineId):
			indent = 0
			for i in range(len(line)):
				if line[i] == '\t':
					indent += 1
				else:
					break
			cutLine = line[indent:]
			task = Task(pageLink, indent, cutLine, [], groupId, lastModif, line, lineId = _lineId)
			return task

		Tasks = []

		r = re.compile(r'((?:(?:TODO|FIXME): .*\n)?\[[ *x]\] .*(?:\n[\t]*\[[ x*]\] .*)*\n)', re.MULTILINE)
		for root, dirs, files in os.walk(NotePath):
			for file in files:
				if file.endswith(".txt"):
					totPath = os.path.join(root, file)
					lastModif = datetime.datetime.fromtimestamp(os.path.getmtime(totPath))
					pageLink = re.sub('^'+NotePath.rstrip('/')+'/', '', os.path.join(root, file)).replace('/', ':')
					pageLink = re.sub('\.txt$', '', pageLink)

					self.allPages.append(pageLink)

					toRead = False
					if (dbNotepgFct(pageLink).count() > 0):
						pg = dbNotepgFct(pageLink).limit(1).get()
						toRead = ((pg.lastModif < lastModif.replace(microsecond=0)) or ((pg.lastModif == lastModif.replace(microsecond=0)) and (pg.lastModifMicroSec < lastModif.microsecond)))
					else:
						toRead = True

					if toRead:
						lock = getLockOn(totPath)
						try:
							lock.acquire()
							f = open(totPath, 'r')
							data = f.read()
						finally:
							lock.release()

						groupId = 1
						lineId = 1
						for res in r.findall(data):
							for line in res.split('\n'):
								if line != '':
									line = line.decode('utf-8')
									task = ParseTask(line.strip('\n'), pageLink, groupId, lastModif, lineId)

									parInd = len(Tasks) - 1
									while (parInd > -1 and Tasks[parInd].indent >= task.indent) :
										parInd -= 1
									if (parInd == -1) :
										task.parent = None
									else :
										task.parent = Tasks[parInd]
										Tasks[parInd].subtasks.append(task)
									Tasks.append(task)
									lineId += 1

							groupId += 1
						

		# Only keep highest level tasks
		newTasks = []
		for task in Tasks:
			if task.getIndentLevel() == 0:
				newTasks.append(task)
		Tasks = newTasks

		# Create a root task
		self.rootTask = Task('', 0, '', Tasks, -1, None, '', parent = None)
		for task in Tasks:
			task.parent = self.rootTask

		# Update tasks with tags, due dates and priorities
		for task in Tasks:
			task.parseTags()
			task.parseDueDates()
			task.parseDuration()
			task.parsePrio()
			task.parseStatus()
			task.parseStarted()
			task.parseNext()
			task.parseComments()
			task.parseDescr()

		# Handle the TODO and FIXME tags
		for i in range(len(Tasks)):
			if ((Tasks[i].params.startswith(u'TODO: ') or Tasks[i].params.startswith(u'FIXME: ')) and i != len(Tasks)-1):
				for j in range(i+1, len(Tasks)):
					if (Tasks[i].fileLink == Tasks[j].fileLink and Tasks[j].groupId == Tasks[i].groupId):
						for tag in Tasks[i].tags:
							Tasks[j].applyTag(tag)
						for dd in Tasks[i].due:
							Tasks[j].applyDueDate(dd)
					else:
						break

		for t in self.rootTask.subtasks:
			if t.fileLink not in self.pages:
				self.pages[t.fileLink] = []
			self.pages[t.fileLink].append(t)

	def PrintAllTasks(self):
		for task in self.rootTask.subtasks:
			task.printToConsole()
					
