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
import ParseNotebook
from ParseNotebook import *
from Lock import *
import peewee
from peewee import *
from flask import Markup, url_for, render_template
from markdown import markdown
from tempfile import mkstemp
from shutil import move, copyfile
from os import remove, close, chmod, urandom, listdir
from datetime import date, datetime, timedelta
import subprocess
from Parameters import *
from werkzeug.security import generate_password_hash, check_password_hash
from jinja2 import Environment, FileSystemLoader
from playhouse.sqliteq import SqliteQueueDatabase
import threading

DEFAULT_SECRETKEY_LEN = 32
NB_PADDING_ZEROS_TGID = 5

class atomicLock:
	def __init__(self, dbo, thrlck):
		self.lock = getLockOn(TaskRootPath + sqlitedbFile, thrlck)
		self.db = dbo

	def __enter__(self):
		thrid = id(threading.current_thread())
		if thrid in self.db.lvls:
			if self.db.lvls[thrid] <= 0:
				self.lock.acquire()
			self.db.lvls[thrid] += 1
		else:
			self.lock.acquire()
			self.db.lvls[thrid] = 1
	
	def __exit__(self, exc_type, exc_val, exc_tb):
		thrid = id(threading.current_thread())
		self.db.lvls[thrid] -= 1
		if self.db.lvls[thrid] <= 0:
			self.lock.release()

class stubAtomic:
	def __enter__(self):
		pass

	def __exit__(self, exc_type, exc_val, exc_tb):
		pass

def getAtomicLock(thrlck = None):
	return db.atomic(thrlck) if type(db) is SqliteFKDatabase else stubAtomic()

class SqliteFKDatabase(SqliteDatabase):
	lvls = {}		
	
	def initialize_connection(self, conn):
		self.execute_sql('PRAGMA foreign_keys=ON;')
		self.execute_sql('PRAGMA journal_mode=WAL;')

	def atomic(self, thrlck = None):
		return atomicLock(self, thrlck)

class MySQLCustomDatabase(MySQLDatabase):
	def atomic(self, thrlck = None):
		return super(MySQLCustomDatabase, self).atomic()

if dbType == 'SQLite':
	db = SqliteFKDatabase(TaskRootPath + sqlitedbFile)
elif dbType == 'MySQL':
	db = MySQLCustomDatabase(dbName, user=dbusr,passwd=dbpwd)
else:
	raise Exception('"' + dbType + '" is not a valid database type (fix TaskList.conf).')

class BaseModel(Model):
    class Meta:
        database = db

class App(BaseModel):
	secretKey = BlobField(null = False)
	mailSenderAddress = CharField()
	mailSendMailPath = TextField()
	allowUserCreation = BooleanField(default = False)
	nologin = BooleanField(default = False)
	localUpdatePeriod = IntegerField(default = 60)

	cssTheme = CharField(default = defaultCSS)

	def GetAllUsers(self):
		return User.select()

	def GetCssURL(self):
		return url_for('static', filename='css/' + self.cssTheme)

	def GetAvailableThemes(self):
		return [file for file in listdir(TaskRootPath + 'static/css/') if file.endswith(".css")]

class User(BaseModel):
	login = CharField(unique = True)
	hash_pwd = CharField()
	isAdmin = BooleanField(default = False)

	calEnable = BooleanField(default = False)
	calURL = TextField(default = '')
	calUsrName = CharField(default = '')
	calPwd = CharField(default = '')

	mailEnable = BooleanField(default = False)
	mailDays = CharField(default = '')
	mailTimes = CharField(default = '')
	mailCategories = TextField(default = '')
	mailAddress = CharField(default = '')
	mailSubject = CharField(default = '')

	cssTheme = CharField(default = defaultCSS)
	colorHighPrio = CharField(default = 'FF0000')
	colorLowPrio = CharField(default = 'FFFF00')
	maxPrio = IntegerField(default = 1)
	
	tagList = TextField(default = '')

	# Optimization fields
	addTaskPreGen = TextField(default = '')
	updatePregenNeeded = BooleanField(default = True)
	tagCloudPreGen = TextField(default = '')
	updateTagCloudPregen = BooleanField(default = True)

	# Local optimization
	addTaskGroupTemp = None
	addTaskTemp = None

	def GetNotePages(self):
		return NotePage.select().join(NoteBook).where(NoteBook.user == self).order_by(NotePage.path)

	def GetAvailableThemes(self):
		return [file for file in listdir(TaskRootPath + 'static/css/') if file.endswith(".css")]

	def GetCssURL(self):
		return url_for('static', filename='css/' + self.cssTheme)
	
	def SetCss(self, name):
		self.cssTheme = name
		pHigh = re.compile('^[\t]*?\.priorityHIGHESTCOLOR { background-color:#(([0-9]?[a-f]?[A-F]?)+); }$')
		pLow = re.compile('^[\t]*?\.priorityLOWESTCOLOR { background-color:#(([0-9]?[a-f]?[A-F]?)+); }$')
		with open(TaskRootPath + 'static/css/' + self.cssTheme) as css:
			for line in css:
				if pHigh.match(line):
					self.colorHighPrio = pHigh.match(line).group(1)
				if pLow.match(line):
					self.colorLowPrio = pLow.match(line).group(1)
		self.save()
		for task in Task.select().join(NotePage).join(NoteBook).where((NoteBook.user == self) & (Task.updatePregenNeeded == False)):
			task.updatePregenNeeded = True
			task.save()

	def GetNbNooks(self):
		return len(NoteBooksPath.split(','))

	# TODO Do something more secure
	def GetCalPwd(self):
		return self.calPwd
	
	def check_password(self, pwd):
		return check_password_hash(self.hash_pwd, pwd)

	def addNotebook(self, name, path, rootPath, url = None, useGit = False, repoPath = None):
		notebook = NoteBook.create(name = name, path = path, url = url, rootPath = rootPath, repoPath = repoPath, useGit = useGit, user = self)
		if notebook.useGit:
			notebook.CreateNotebookGitHooks()
		return notebook

	def updateMaxPrio(self, prio = None):
		changed = False
		if prio is not None:
			if prio > self.maxPrio:
				self.maxPrio = prio
				changed = True
		else:
			max_prio = [tmp.priority for tmp in Task.select().join(NotePage).join(NoteBook).where(NoteBook.user == self).order_by(Task.priority.desc()).limit(1).get()]
			if (len(max_prio) > 0) and max_prio[0] > self.maxPrio:
				self.maxPrio = max_prio[0]
				changed = True

		if changed:
			# Propagate the need to update to all tasks
			self.save()
			for task in Task.select().join(NotePage).join(NoteBook).where((NoteBook.user == self) & (Task.updatePregenNeeded == False)):
				task.updatePregenNeeded = True
				task.save()

	def updateSpecifTag(self, tagId):
		tl = self.tagList.split(u' ')
		try:
			ind = tl.index(u'id_' + unicode(tagId))
			tl[ind+1] = unicode(int(tl[ind+1])+1)
			self.tagList = u' '.join(tl)
		except ValueError:
			self.tagList += u'id_' + unicode(tagId) + u' 1 '
		self.updateTagCloudPregen = True
		self.save()

	def removeTagList(self, tagsToRemove):
		tl = self.tagList.split(u' ')
		for tag in tagsToRemove:
			try:
				ind = tl.index(u'id_' + unicode(tag.id))
				if int(tl[ind+1]) > 1:
					tl[ind+1] = unicode(int(tl[ind+1])-1)
				else:
					tl = tl[:ind] + tl[ind+2:]
			except ValueError:
				pass
		self.tagList = u' '.join(tl)
		self.updateTagCloudPregen = True
		self.save()

	def getAddTaskPregenHTML(self):
		if self.updatePregenNeeded:
			self.generatePreGen()
		return Markup(self.addTaskPreGen)

	def getTagCloudHTML(self):
		if self.updateTagCloudPregen:
			self.generateTagCloudPreGen()
		return Markup(self.tagCloudPreGen)
			
	def generatePreGen(self):
		if User.addTaskGroupTemp is None or User.addTaskTemp is None:
			env = Environment(loader=FileSystemLoader([TaskRootPath + 'templates', TaskRootPath + 'static/css']))
			User.addTaskGroupTemp = env.get_template('addTaskGroup.html')
			User.addTaskTemp = env.get_template('addTask.html')
		addTgStr = User.addTaskGroupTemp.render(user = self, taskgroupid = -1, addTaskHeader = True)
		addTskStr = User.addTaskTemp.render(user = self, taskid = -1, addType = 'AddTask', tasktype = 'norm', addTaskHeader = True)
		self.addTaskPreGen = addTgStr + addTskStr
		self.updatePregenNeeded = False
		self.save()

	def generateTagCloudPreGen(self):
		minSize = 10
		maxSize = 20
		html = u''
		nbTags = []
		contentTag = []
		maxNbTag = 0
		minNbTag = 99999
		tl = self.tagList.split(u' ')
		for i in range(0, len(tl)-1, 2):
			try:
				contentTag.append(Tag.get(Tag.id == int(tl[i][3:])))
				nbTags.append(int(tl[i+1]))
			except Exception:
				continue
			if nbTags[-1] > maxNbTag:
				maxNbTag = nbTags[-1]
			if nbTags[-1] < minNbTag:
				minNbTag = nbTags[-1]

		for (tag, nb) in [(contentTag[i], nbTags[i]) for i in sorted(range(len(nbTags)), key = lambda x:nbTags[x], reverse=True)]:
			if maxNbTag > minNbTag:
				html += tag.html(str(int(minSize + (maxSize - minSize) * (float(nb - minNbTag) / float(maxNbTag - minNbTag))**0.3)))
			else:
				html += tag.html(str(int(minSize + (maxSize - minSize) * 0.5)))

		self.tagCloudPreGen = html
		self.updateTagCloudPregen = False
		self.save()

class NoteBook(BaseModel):
	name = CharField()
	path = CharField()
	url = TextField(null = True)
	rootPath = TextField()
	repoPath = TextField(null = True)
	useGit = BooleanField(default = False)
	user = ForeignKeyField(User, related_name = 'notebooks', on_delete='CASCADE')
	needsCommit = BooleanField(default = False)

	class Meta:
		indexes = (
			(('user', 'path'), True),
		)

	def GetNotePages(self):
		return self.notePages.order_by(NotePage.path)

	def CommitNeeded(self):
		if self.useGit:
			self.needsCommit = True
			self.save()

	def CommitIfNeeded(self, doDbCommit = True):
		if self.needsCommit and self.useGit:
			# First commit the database transaction, to avoid running UpdateDB.py while the first transaction is not commited yet
			self.needsCommit = False;
			self.save()
			if doDbCommit:
				db.commit()
			# Then run the commit script
			scriptPath = TaskRootPath + 'NotesGitCommitPush.sh'
			subprocess.Popen(scriptPath + ' ' + self.rootPath + ' ' + self.rootPath.replace('/', '_').replace('~', '_') + ' &', shell=True)

	def CreateNotebookGitHooks(self):
		if self.useGit and self.repoPath != '':
			print(u'Updating git hooks for user: ' + self.user.login)
			hookPath = self.repoPath + 'hooks/post-receive'
			pullCmdStr = 'git --git-dir ' + self.rootPath + '.git --work-tree ' + self.rootPath + ' pull\n'
			updateCmdRad = 'cd ' + TaskRootPath + '; python UpdateDB.py '
			updateCmdStr = updateCmdRad + self.user.login + ' 2>/dev/null >/dev/null &\n'
			pullOk = False
			updateOk = False
			p = re.compile('^' + re.escape(updateCmdRad) + '(.+?) 2>/dev/null >/dev/null &$')
			uLogs = [u.login for u in User.select().join(NoteBook).where(NoteBook.rootPath == self.rootPath).distinct()]

			lock = getLockOn(hookPath)
			try:
				lock.acquire()
				fh, tmpPath = mkstemp()
				with open(tmpPath, 'w') as new_file:
					with open(hookPath, 'r') as old_file:
						for line in old_file:
							tmpLine = unicode(line, 'utf-8')
							if tmpLine.find(pullCmdStr) != -1:
								pullOk = True
							if tmpLine.find(updateCmdStr) != -1:
								updateOk = True
							m = p.match(tmpLine)
							if tmpLine != u'wait\n' and ((not m) or (m.group(1) in uLogs)):
								new_file.write(tmpLine.encode('utf-8', 'replace'))
						if not pullOk:
							new_file.write(pullCmdStr)
						if not updateOk:
							new_file.write(updateCmdStr)
				close(fh)
				copyfile(tmpPath, hookPath)
				remove(tmpPath)
			finally: 
				lock.release()

	def RemoveNotebookGitHooks(self):
		if self.useGit and self.repoPath != '':
			hookPath = self.repoPath + 'hooks/post-receive'
			updateCmdRad = 'cd ' + TaskRootPath + '; python UpdateDB.py '
			updateCmdStr = updateCmdRad + self.user.login + ' 2>/dev/null >/dev/null &\n'
			needWait = False
			lock = getLockOn(hookPath)
			try:
				lock.acquire()
				fh, tmpPath = mkstemp()
				with open(tmpPath, 'w') as new_file:
					with open(hookPath, 'r') as old_file:
						for line in old_file:
							tmpLine = unicode(line, 'utf-8')
							if tmpLine.find(updateCmdStr) == -1:
								new_file.write(tmpLine.encode('utf-8', 'replace'))
							elif u'; python UpdateDB.py ' in tmpLine:
								needWait = True
					if needWait:
						new_file.write(u'wait\n')
				close(fh)
				copyfile(tmpPath, hookPath)
				remove(tmpPath)
			finally:
				lock.release()

	def UpdateTaskPregen(self):
		for task in Task.select().join(NotePage).where(NotePage.book == self):
			task.updatePregenNeeded = True
			task.save()

class NotePage(BaseModel):
	path = CharField()
	lastModif = DateTimeField()
	lastModifMicroSec = IntegerField()
	book = ForeignKeyField(NoteBook, related_name = 'notePages', on_delete='CASCADE')

	class Meta:
		indexes = (
			(('book', 'path'), True),
		)

	def addTask(self, text):
		return self.addTaskGroup('None', '', text)

	def addTaskGroup(self, tgType, tgText, tskText):
		return TaskGroup.select().join(Task).where(Task.parentPage == self).group_by(TaskGroup.id).order_by(TaskGroup.name.desc()).limit(1).get().addTaskGroup(tgType, tgText, tskText, True)

	def getTaskGroups(self):
		return TaskGroup.select().join(Task).where(Task.parentPage == self).distinct()

	def getFilePath(self):
		FilePath = self.book.path + self.path.replace(':', '/') + '.txt'
		if type(FilePath) is unicode:
			pass
		else:
			FilePath = unicode(FilePath, 'utf-8', 'replace')
		FilePath = FilePath.encode('utf-8')
		return FilePath

	def updatedFile(self):
		lastModif = datetime.fromtimestamp(os.path.getmtime(self.getFilePath()))
		if (self.lastModif < lastModif.replace(microsecond=0)) or ((self.lastModif == lastModif.replace(microsecond=0)) and (self.lastModifMicroSec < lastModif.microsecond)):
			self.lastModif = lastModif
			self.lastModifMicroSec = lastModif.microsecond
			self.save()

	def getHierarchicalViewName(self):
		allPaths = [np.path for np in self.book.GetNotePages()]
		ind = allPaths.index(self.path)
		pth = self.path.split(':')
		if ind > 0:
			prevPth = allPaths[ind-1].split(':')
		else:
			prevPth = []
		name = u''
		for i, val in enumerate(pth):
			if i < len(prevPth):
				if prevPth[i] == val:
					name += '&nbsp;'*(len(val)+(1 if i > 0 else 0))
					continue
			name += (u':' if i > 0 else u'') + val
		return Markup(name)

class TaskGroup(BaseModel):
	name = CharField()
	descr = TextField()

	# Optimization fields
	markupContent = TextField(default = '')
	state = IntegerField(default = 0)
	needsUpdate = BooleanField(default = True)

	addTaskGroupPreGen = TextField(default = '')
	updatePregenNeeded = BooleanField(default = True)

	# Local optimization
	addTaskGroupTemp = None

	def isToUser(self, user):
		if self.tasksingroup.count() > 0:
			return self.tasksingroup[0].parentPage.book.user == user
		else:
			return False

	def addTaskGroup(self, tgType, tgText, tskText, below):
		if tgType != u'None':
			texttg = unicode(Markup(tgType) + u': ' + Markup.escape(tgText))
		else:
			texttg = u''
		texttsk = unicode(Markup(u'[ ] ') + Markup.escape(tskText))
		task = ParseNotebook.Task('FakePageLink', 0, texttsk, [], -1, date.today(), texttsk, -1)
		task.parseAll()

		if below:
			relTask = self.GetLastTask()
		relLineId = relTask.lineId
		relTaskPosition = relTask.findIndAmongSameTasks()
		# Find groupId
		notePg = self.tasksingroup.get().parentPage
		tgNamePrefix = notePg.book.user.login + '_/_' + notePg.book.path + '_/_' + notePg.path + '_/_'
		pgroupId = re.compile(tgNamePrefix + '([0-9]+)')
		groupId = int(pgroupId.match(self.name).group(1))
		# Add taskgroup to database
		tgName = tgNamePrefix + format(groupId + 1, '0' + str(NB_PADDING_ZEROS_TGID))
		tg = TaskGroup.create(name = tgName, descr = texttg)
		tg.markupContent = ParseMarkup(texttg, notePg, notePg.book.url)
		tg.save()
		# Add Task to database
		tsk = Task.create(content = task.descr, fullLine = texttsk, priority = task.prio, state = 0, started = task.started, duration = task.duration, parentPage = notePg, group = tg, parent = None, previous = None, lineId = relLineId + 2, mostUrgentDate = None, actionable = True, lastMailReminder = None)
		# Add tags
		for tag in task.tags:
			AddTag(tag, tsk)
		for tag in tg.getGroupTags():
			AddTag(tag, tsk)
		# Add duedates
		for dd in task.due:
			AddDueDate(dd, tsk)
		tsk.markupContent = ParseMarkup(tsk.content, tsk.parentPage, tsk.parentPage.book.url)
		tsk.save()
		# Change lineIds of tasks after the task that will be added
		afterTasks = Task.select().where((Task.parentPage == notePg) & (Task.lineId > relTask.lineId) & (Task.id != tsk.id))
		for aftTsk in afterTasks:
			aftTsk.lineId += 2
			aftTsk.save()
		# Change taskgroupnames after added taskgroup 
		afterTgs = TaskGroup.select().where(TaskGroup.name % (tgNamePrefix + '%'))
		for afttg in afterTgs:
			gId = int(pgroupId.match(afttg.name).group(1))
			if (gId > groupId) and (afttg.id != tg.id):
				afttg.name = tgNamePrefix + str(gId + 1)
				afttg.save()
		# Add task to file
		FilePath = notePg.getFilePath()
		if texttg != u'':
			text = unicode(u'\n' + texttg + u'\n' + texttsk + u'\n')
		else:
			text = unicode(u'\n' + texttsk + u'\n')
		#Create temp file
		lock = getLockOn(FilePath)
		found = False
		try:
			lock.acquire()
			fh, tmpPath = mkstemp()
			oldmask = os.umask(002)
			with open(tmpPath, 'w') as new_file:
				with open(FilePath, 'r') as old_file:
					tmpVal = 0
					for line in old_file:
						tmpLine = unicode(line, 'utf-8')
						new_file.write(tmpLine.encode('utf-8', 'replace'))
						if unicode(relTask.fullLine + '\n') == tmpLine:
							if tmpVal == relTaskPosition:
								found = True
								new_file.write(text.encode('utf-8', 'replace'))
							tmpVal += 1
			close(fh)
			#Move new file
			copyfile(tmpPath, FilePath)
			remove(tmpPath)
			os.umask(oldmask)
		finally:
			lock.release()

		if found:
			self.tasksingroup[0].parentPage.updatedFile()
			# Commit changes
			notePg.book.CommitNeeded()
			notePg.book.CommitIfNeeded()
		else:
			runUpdate(self.tasksingroup[0].parentPage.book.user.login)
			raise Exception('The previous task was not found in the file.')

		return tsk.id

	def GetFirstTask(self):
		return slef.tasksingroup.order_by(Task.lineId).limit(1).get()

	def GetLastTask(self):
		return self.tasksingroup.order_by(Task.lineId.desc()).limit(1).get().GetLastSubTask()

	def updateState(self, state, preventCommit = False):
		for task in self.tasksingroup:
			task.updateState(state, True)
		if not preventCommit:
			self.tasksingroup.get().parentPage.book.CommitIfNeeded()

	def containsTag(self, tagName):
		conttag = False;
		for task in self.tasksingroup:
			conttag |= task.containsTag(tagName)
			if conttag:
				break
		return conttag;

	def getGroupTags(self):
		p = re.compile(' @[a-z|A-Z|0-9]+')
		return [tag[1:] for tag in p.findall(self.descr)]

	def containsRegExp(self, regexp):
		tmp = len(regexp.findall(self.descr)) > 0
		for task in self.tasksingroup:
			tmp |= task.containsRegExp(regexp)
		for com in self.taskGroupComment:
			tmp |= com.containsRegExp(regexp)
		return tmp

	def getState(self):
		if self.needsUpdate:
			self.state = Task.select(fn.Min(Task.state)).where(Task.group == self).group_by(Task.group).scalar()
			self.needsUpdate = False
			self.save()
		return self.state

	def GetStatusButtonVal(self, val):
		return 'status' + unicode(self.id) + '_' + unicode(val % 3)

	def getDuration(self):
		duration = 0
		for task in self.tasksingroup:
			if task.duration:
				duration += task.getDuration()
		return duration

	def getAddTaskGroupPregenHTML(self):
		if self.updatePregenNeeded:
			self.generatePreGen()
		return Markup(self.addTaskGroupPreGen)

	def generatePreGen(self):
		if TaskGroup.addTaskGroupTemp is None:
			env = Environment(loader=FileSystemLoader([TaskRootPath + 'templates', TaskRootPath + 'static/css']))
			TaskGroup.addTaskGroupTemp = env.get_template('addTaskGroup.html')
		self.addTaskGroupPreGen = TaskGroup.addTaskGroupTemp.render(taskgroupid = self.id, addTaskHeader = False)
		self.updatePregenNeeded = False
		self.save()

class TaskGroupComment(BaseModel):
	idTaskGroup = ForeignKeyField(TaskGroup, related_name = 'taskGroupComment', on_delete='CASCADE')
	content = TextField()

	def html(self):
		return Markup(ParseMarkup(self.content, [res for res in NotePage.select().join(Task).join(TaskGroup).where(TaskGroup.id == self.idTaskGroup)][0], Task.get(Task.group == self.idTaskGroup).parentPage.book.url))

	def containsRegExp(self, regexp):
		return len(regexp.findall(self.content)) > 0

class Tag(BaseModel):
	name = CharField(unique = True)
	parent = ForeignKeyField('self', null=True, related_name='children')

	def html(self, ftSize = -1):
		if ftSize == -1:
			return Markup(u'<form action="." class="tagform" method="post"><button class="TagButton" type="submit" value="' + self.name + u'" name="' + self.name + u'">' + self.name + u'</button></form>')
		else:
			return Markup(u'<form action="." class="tagform" method="post"><button class="TagButton" type="submit" value="' + self.name + u'" name="' + self.name + u'"><span style="font-size:' + unicode(ftSize) + u'px">' + self.name + u'</span></button></form>')
		
class DueDate(BaseModel):
	date = DateField()
	origDate = DateField()
	cycleCounter = IntegerField()
	# if all cyclic fields are 0, it only happens once, else it gets repeated every cyclic period
	cyclic_y = IntegerField()
	cyclic_m = IntegerField()
	cyclic_d = IntegerField()

	def html(self):
		html = '<div class="'
		if self.date <= date.today():
			html += 'dateUrgent'
		elif self.date <= date.today() + timedelta(2):
			html += 'dateImportant'
		else:
			html += 'dateOk'
		html += '">' + str(self.date)
		if self.cyclic_y + self.cyclic_m + self.cyclic_d > 0:
			html += '</br><span class="cyclicDateSpan">(every'
			if self.cyclic_y > 0:
				html += ' ' + str(self.cyclic_y) + ' year' + ('s' if self.cyclic_y > 1 else '')
			if self.cyclic_m > 0:
				html += ' ' + str(self.cyclic_m) + ' month' + ('s' if self.cyclic_m > 1 else '')
			if self.cyclic_d > 0:
				html += ' ' + str(self.cyclic_d) + ' day' + ('s' if self.cyclic_d > 1 else '')
			html += ')</span>'
		html += '</div>'
		return Markup(html)
	

class Task(BaseModel):
	content = TextField()
	fullLine = TextField()
	priority = IntegerField()
	state = IntegerField()
	started = IntegerField()
	duration = IntegerField(null = True) # Duration in seconds
	parentPage = ForeignKeyField(NotePage, related_name = 'tasksinpage')
	group = ForeignKeyField(TaskGroup, null=True, related_name='tasksingroup', on_delete='SET NULL')
	parent = ForeignKeyField('self', null=True, related_name='children', on_delete='SET NULL')
	previous = ForeignKeyField('self', null=True, related_name='next', on_delete='SET NULL')
	lineId = IntegerField()

	# Optimization fields
	mostUrgentDate = ForeignKeyField(DueDate, null=True, related_name='urgentForTask')
	markupContent = TextField(default = '')
	actionable = BooleanField()
	markupTags = TextField(default = '')
	preGen1 = TextField(default = '')
	preGen2 = TextField(default = '')
	preGen3 = TextField(default = '')
	preGen4 = TextField(default = '')
	preGen5 = TextField(default = '')
	addPreGen1 = TextField(default = '')
	addPreGen2 = TextField(default = '')
	updatePregenNeeded = BooleanField(default = True)
	lastUpdate = DateField(null = True)
	# mailing stuff
	lastMailReminder = DateTimeField(null = True)

	# Local optimization
	taskIntTemp = None
	addTaskTemp = None

	@staticmethod
	def withUser(user):
		return Task.select(Task, NotePage, NoteBook).join(NotePage).join(NoteBook).where(NoteBook.user == user)

	def updateFile(self):
		symbols = [' ', '*', 'x']
		FilePath = self.parentPage.getFilePath()
		# Update state
		p = re.compile('^[\t]*?\[([*x ])\]')
		m = p.match(self.fullLine)
		tmpFullLine = unicode(self.fullLine)
		newLine = tmpFullLine[0:m.start(1)] + unicode(symbols[self.state]) + tmpFullLine[m.end(1):]
		# Add started tag if needed
		m2 = re.compile('^ Started: ').match(tmpFullLine[m.end(1)+1:])
		if self.started == 1 and not m2:
			newLine = newLine[0:m.end(1)+2] + 'Started: ' + newLine[m.end(1)+2:]
		elif self.started == 0 and m2:
			newLine = newLine[0:m.end(1)+1+m2.start(0)+1] + newLine[m.end(1)+1+m2.end(0):]
		# Add comments if needed
		for com in self.comments:
			if newLine.find(com.content) == -1:
				newLine += ' [' + com.content + ']'
		# Update cyclic dates
		dates = DueDate.select().join(TaskDates).where(TaskDates.from_task == self, ((DueDate.cyclic_y != 0) | (DueDate.cyclic_m != 0) | (DueDate.cyclic_d != 0)), TaskDates.parentDate == False)
		p = re.compile('\[d: ([0-9]+[-/][0-9]+[-/][0-9]+)( *)(c[0-9|dmy]+)\]')
		if dates.count() > 0 and len(p.findall(newLine)) == dates.count():
			dds = [d for d in dates]
			ind = 0
			for it in p.finditer(newLine):
				cyclicStr = 'c'
				cyclicStr += ((str(dds[ind].cyclic_y) + 'y') if dds[ind].cyclic_y > 0 else '')
				cyclicStr += ((str(dds[ind].cyclic_m) + 'm') if dds[ind].cyclic_m > 0 else '')
				cyclicStr += ((str(dds[ind].cyclic_d) + 'd') if dds[ind].cyclic_d > 0 else '')
				newLine = newLine[0:it.start(1)] + dds[ind].date.strftime('%Y-%m-%d') + it.group(2) + cyclicStr + newLine[it.end(3):]
				ind += 1
		# Check if other tasks have the same fullLine
		prevTaskPosition = self.findIndAmongSameTasks()
		#Create temp file
		lock = getLockOn(FilePath)
		found = False
		try:
			lock.acquire()
			fh, tmpPath = mkstemp()
			oldmask = os.umask(002)
			with open(tmpPath, 'w') as new_file:
				with open(FilePath, 'r') as old_file:
					tmpVal = 0
					for line in old_file:
						tmpLine = unicode(line, 'utf-8')
						if unicode(self.fullLine + '\n') == tmpLine:
							if tmpVal == prevTaskPosition:
								new_file.write((newLine + '\n').encode('utf-8', 'replace'))
								found = True
							else:
								new_file.write(tmpLine.encode('utf-8', 'replace'))
							tmpVal += 1
						else:
							new_file.write(tmpLine.encode('utf-8', 'replace'))
			close(fh)
			#Move new file
			copyfile(tmpPath, FilePath)
			remove(tmpPath)
			os.umask(oldmask)
		finally:
			lock.release()

		if found:
			self.parentPage.updatedFile()

			self.fullLine = newLine.encode('utf-8', 'replace')
			self.save()

			self.parentPage.book.CommitNeeded()
		else:
			runUpdate(self.parentPage.book.user.login)
			raise Exception('The task was not found in the file.')

	def findIndAmongSameTasks(self):
		sameTasks = Task.select().join(NotePage).join(NoteBook).where((NoteBook.user == self.parentPage.book.user) & (Task.parentPage == self.parentPage) & (Task.fullLine % self.fullLine.replace('%', '\%'))).order_by(Task.lineId)
		prevTaskPosition = 0
		tmpVal = 0
		for st in sameTasks:
			if st.id == self.id:
				prevTaskPosition = tmpVal
			tmpVal += 1
		return prevTaskPosition

	def addTask(self, text, asChild):
		text = unicode(Markup(u'[ ] ') + Markup.escape(text))
		task = ParseNotebook.Task('FakePageLink', 0, text, [], -1, date.today(), text, -1)
		task.parseAll()
		p = re.compile('(^[\t]*)[^\t]+')
		text = p.match(self.fullLine).group(1) + text
		if asChild:
			text = '\t' + text

		prevTask = self.GetLastSubTask()
		prevLineId = prevTask.lineId
		notePg = self.parentPage
		# Check if other tasks contains the same text as prevTask
		prevTaskPosition = prevTask.findIndAmongSameTasks()
		# Add task to database
		_parent = self if asChild else self.parent
		_previous = ((prevTask if prevTask != self else None) if asChild else self) if task.previousTask else None
		tsk = Task.create(content = task.descr, fullLine = text, priority = task.prio, state = 0, started = task.started, duration = task.duration, parentPage = notePg, group = self.group, parent = _parent, previous = _previous, lineId = prevLineId + 1, mostUrgentDate = None, actionable = False, lastMailReminder = None)
		tsk.actionable = tsk.isActionable()
		tsk.save()
		# Update user values
		tsk.parentPage.book.user.updateMaxPrio(tsk.priority)
		# Add tags
		for tag in task.tags:
			AddTag(tag, tsk)
		for tag in self.group.getGroupTags():
			AddTag(tag, tsk)
		# Add duedates
		for dd in task.due:
			AddDueDate(dd, tsk)
		tsk.markupContent = ParseMarkup(tsk.content, tsk.parentPage, tsk.parentPage.book.url)
		tsk.save()
		# Change lineIds of tasks after the task that will be added
		afterTasks = Task.select().where((Task.parentPage == notePg) & (Task.lineId > prevTask.lineId) & (Task.id != tsk.id))
		for aftTsk in afterTasks:
			aftTsk.lineId += 1
			aftTsk.save()
		# Update group
		if self.group:
			self.group.needsUpdate = True
			self.group.save()
		# Add task to file
		FilePath = notePg.getFilePath()
		text = unicode(text + u'\n')
		#Create temp file
		lock = getLockOn(FilePath)
		try:
			lock.acquire()
			fh, tmpPath = mkstemp()
			oldmask = os.umask(002)
			found = False
			with open(tmpPath, 'w') as new_file:
				with open(FilePath, 'r') as old_file:
					tmpVal = 0
					for line in old_file:
						tmpLine = unicode(line, 'utf-8')
						new_file.write(tmpLine.encode('utf-8', 'replace'))
						if unicode(prevTask.fullLine + '\n') == tmpLine:
							if tmpVal == prevTaskPosition:
								new_file.write(text.encode('utf-8', 'replace'))
								found = True
							tmpVal += 1
			close(fh)
			#Move new file
			copyfile(tmpPath, FilePath)
			remove(tmpPath)
			os.umask(oldmask)
		finally:
			lock.release()

		if found:
			self.parentPage.updatedFile()
			# Commit changes
			self.parentPage.book.CommitNeeded()
			self.parentPage.book.CommitIfNeeded()
		else:
			runUpdate(self.parentPage.book.user.login)
			raise Exception('The base task was not found in the file.')

		return tsk.id

	def GetLastSubTask(self):
		if self.children.count() > 0:
			return self.children.order_by(Task.lineId.desc()).limit(1).get().GetLastSubTask()
		else:
			return self

	def addComment(self, com):
		fullCom = Markup(u'[comment: [' + unicode(date.today()) + u']> ') + Markup.escape(com) + Markup(u']')
		Comment.create(idTask = self, content = unicode(fullCom[1:-1]))
		self.updateFile()
		self.parentPage.book.CommitIfNeeded()
		self.updatePregenNeeded = True
		self.save()

	def updateState(self, state, preventCommit = False, updateParent = True, updateChild = True):
		self.state = state
		if state > 0 and self.started == 1:
			self.started = 0
		self.save()
		# Update children
		if updateChild and (state > 0):
			for tsk in self.children:
				if tsk.state == 0:
					tsk.updateState(state, True, False, True)
		# Update parent
		if updateParent and self.parent and (self.parent.state != self.parent.getStateFromChildren()):
			self.parent.updateState(self.parent.getStateFromChildren(), True, True, False)
		self.updateFile()
		if not preventCommit:
			self.parentPage.book.CommitIfNeeded()
		# Update actionable
		self.actionable = self.isActionable()
		if self.group:
			self.group.needsUpdate = True
			self.group.save()
		self.updatePregenNeeded = True
		self.save()
		# Update next
		if self.next.count() > 0:
			nxt = self.next.get()
			nxt.actionable = nxt.isActionable()
			nxt.updatePregenNeeded = True
			nxt.save()

	def updateStarted(self, strt):
		self.started = strt
		self.updatePregenNeeded = True
		self.save()
		self.updateFile()
		self.parentPage.book.CommitIfNeeded()

	def getStateFromChildren(self):
		allOk = True
		for tsk in self.children:
			if tsk.state == 0:
				allOk = False
		if allOk:
			return self.state
		else:
			return 0

	def isActionable(self):
		act = True;
		if self.previous:
			act = (self.previous.state > 0)
		elif self.parent:
			act = self.parent.isActionable()
		return act;

	def containsTag(self, tagName):
		conttag = tagName in self.markupTags
		if not conttag:
			for child in self.children:
				conttag |= child.containsTag(tagName)
				if conttag:
					break
		return conttag

	def containsRegExp(self, regexp):
		tmp = len(regexp.findall(self.content)) > 0
		for com in self.comments:
			tmp |= com.containsRegExp(regexp)
		for sub in self.children:
			tmp |= sub.containsRegExp(regexp)
		return tmp

	def getDuration(self):
		return self.duration

	def GetStatusButtonVal(self, val):
		return u'status' + unicode(self.id) + '_' + unicode(val % 3)

	def GetPriorityColor(self, colorHighPrio, colorLowPrio, maxPrio):
		colHigh = [int(colorHighPrio[(2*i):(2*i+2)], 16) for i in range(0,3)]
		colLow = [int(colorLowPrio[(2*i):(2*i+2)], 16) for i in range(0,3)]
		ret = ''
		ratio = float(self.priority)/float(maxPrio) if maxPrio > 0 else 0
		for i in range(0, 3):
			ret += unicode(int((ratio * colHigh[i] + (1.0 - ratio) * colLow[i])))
			if i < 2:
				ret += ', '
		return ret

	def GetStartButtonVal(self):
		return 'start_' + unicode(self.id) + '_' + unicode((self.started + 1) % 2)

	def GetPriorityStr(self):
		return unicode(self.priority)

	def GetDurationStr(self):
		return printDuration(self.getDuration())

	def GetDueDates(self):
		return DueDate.select().join(TaskDates).where(TaskDates.from_task == self.id).order_by(DueDate.date)

	def getDueDateClassName(self):
		tmpstr = u'duedates'
		if self.mostUrgentDate:
			if self.mostUrgentDate.date <= date.today():
				tmpstr += u'Urgent'
			elif self.mostUrgentDate.date <= date.today() + timedelta(2):
				tmpstr += u'Important'
			else:
				tmpstr += u'Ok'
		return tmpstr

	def taskIntClass(self):
		html = '"'
		if self.started > 0:
			html += u'taskStarted'
		elif self.actionable:
			html += u'taskInt'
		else:
			html += u'taskDisabled'
		return Markup(html + '"')

	def getHtml(self, pageMngr):
		if self.updatePregenNeeded or (not self.lastUpdate or self.lastUpdate < date.today()):
			self.generatePreGen()
		return Markup(self.preGen1) + pageMngr.ParseAndHighlight(self.markupContent) + Markup(self.preGen2) + pageMngr.ParseAndHighlight(self.markupTags) + Markup(self.preGen3) + pageMngr.ParseAndHighlight(self.preGen4) + Markup(self.preGen5)

	def getAddSubTaskHtml(self):
		return Markup(self.addPreGen1)

	def getAddTaskHtml(self):
		return Markup(self.addPreGen2)

	def getFullHtml(self, pageMngr):
		retVal = self.getHtml(pageMngr)
		retVal += Markup('<div class="subtask">' if self.children.where(pageMngr.GetSubTaskFilter()).count() > 0 else '<div class="subtask", id="SubTask' + str(self.id) + '", style="display:none">')
		for task in self.children.where(pageMngr.GetSubTaskFilter()).order_by(pageMngr.GetSubTaskOrdering()):
			retVal += task.getFullHtml(pageMngr)
		retVal += self.getAddSubTaskHtml() + Markup('</div>') + self.getAddTaskHtml()
		return retVal

	def generatePreGen(self):
		if Task.taskIntTemp is None or Task.addTaskTemp is None:
			env = Environment(loader=FileSystemLoader([TaskRootPath + 'templates', TaskRootPath + 'static/css']))
			Task.taskIntTemp = env.get_template('taskInt.html')
			Task.addTaskTemp = env.get_template('addTask.html')
		taskStr = Task.taskIntTemp.render(task=self, colorHighPrio = self.parentPage.book.user.colorHighPrio, colorLowPrio = self.parentPage.book.user.colorLowPrio, maxPrio = self.parentPage.book.user.maxPrio)
		tss = taskStr.split('<!-- PreGen -->')
		self.preGen1 = tss[0]
		self.preGen2 = tss[1]
		self.preGen3 = tss[2]
		self.preGen4 = tss[3]
		self.preGen5 = tss[4]
		self.addPreGen1 = Task.addTaskTemp.render(taskid=self.id, addType='AddSubTask', tasktype = 'sub')
		self.addPreGen2 = Task.addTaskTemp.render(taskid=self.id, addType='AddTask', tasktype = 'norm')
		self.updatePregenNeeded = False
		self.lastUpdate = date.today()
		self.save()
	
class Comment(BaseModel):
	idTask = ForeignKeyField(Task, related_name='comments', on_delete='CASCADE')
	content = TextField()

	def html(self):
		return Markup(ParseMarkup(self.content, self.idTask.parentPage, self.idTask.parentPage.book.url))

	def containsRegExp(self, regexp):
		return len(regexp.findall(self.content)) > 0

class TaskDates(BaseModel):
	from_task = ForeignKeyField(Task, related_name='dueDates', on_delete='CASCADE')
	to_date = ForeignKeyField(DueDate, related_name='related_tasks_date', on_delete='CASCADE')
	parentDate = BooleanField(default = 'False')

	class Meta:
		indexes = (
			(('from_task', 'to_date'), True),
		)
		primary_key = CompositeKey('from_task', 'to_date')

class TaskTags(BaseModel):
	from_task = ForeignKeyField(Task, related_name='tags', on_delete='CASCADE')
	to_tag = ForeignKeyField(Tag, related_name='related_tasks_tag', on_delete='CASCADE')

	class Meta:
		indexes = (
			(('from_task', 'to_tag'), True),
		)
		primary_key = CompositeKey('from_task', 'to_tag')

# parse a content for links of the type [[ :dijz:dqzd:dqz ]] and replace to html links
def ParseMarkup(content, page, noteURL):
	res = Markup(content)
	# try to find tags
	p = re.compile('( (@[0-9a-zA-Z]+))')
	for tag in p.findall(res):
		tmpTag = Tag.select().where(Tag.name == tag[1])
		if tmpTag.count() > 0:
			res = res.replace(tag[0], ' ' + Tag.get(Tag.name == tag[1]).html())
	# try to find URL
	p = re.compile('[a-z]+://(?:[^[ \(\)]]*(?:\([^ ]*?\))*)+')
	for link in p.findall(res):
		res = res.replace(link, Markup('<a href="') + link + Markup('", target="_blank">') + link + Markup('</a>'))
	# try to find zim-style links (enclosed in [[ ]])
	p = re.compile('(\[\[ *([^\]]*) *\]\])')
	for link in p.findall(content):
		url =  link[1].replace(':', '/') + '.html'
		if not url.startswith('/'):
			localPath = ''
			for fold in page.path.split(':')[0:-1]:
				localPath += fold + '/'
			url = '/' + localPath + url
		url = noteURL + url
		res = res.replace(link[0], Markup('<a href="') + url + Markup('", target="_blank">') + link[1] + Markup('</a>'))
	# try to find images (enclosed in {{ }})
	p = re.compile('({{(.+?\.png).*?}})')
	for img in p.findall(content):
		url = noteURL + '/' + page.path.replace(':', '/') + '/' + img[1].strip('./')
		res = res.replace(img[0], Markup('<img src="') + url + Markup('">'))
	# try to find text that needs coloring
	p = re.compile('^comment: \[[0-9]+[-/][0-9]+[-/][0-9]+\]>')
	for comHeader in p.findall(res):
		res = res.replace(comHeader, Markup('<span class="comheader">') + comHeader + Markup('</span>'))
	return unicode(res)

def printDuration(dur):
	mults = [(24*60*60, 'd'), (60*60, 'h'), (60, 'm'), (1, 's')]
	tmp = dur
	res = ''
	for (m, c) in mults:
		if tmp / m > 0:
			res += str(tmp / m) + c
			tmp = tmp % m
	return res

def InsertTaskInDb(task, par, _prev, notePg, idsDict = {}, tgIdsDict = {}):
	# TaskState
	tskstate = 0
	tsk = None
	tgComment = ''
	if task.status == '*':
		tskstate = 1
	elif task.status == 'x':
		tskstate = 2
	elif task.status == 's':
		tskstate = 3
		tgComment = task.descr

	prev = None
	if task.previousTask:
		prev = _prev

	# TaskGroup
	tg = None
	tgName = notePg.book.user.login + '_/_' + notePg.book.path + '_/_' + task.fileLink + '_/_' + format(task.groupId, '0' + str(NB_PADDING_ZEROS_TGID))
	try:
		tg = TaskGroup.get(TaskGroup.name == tgName)
	except:
		if tgName in tgIdsDict:
			tg = TaskGroup.create(id = tgIdsDict[tgName], name = tgName, descr = tgComment)
		else:
			tg = TaskGroup.create(name = tgName, descr = tgComment)
		
	tg.markupContent = ParseMarkup(tg.descr, notePg, notePg.book.url)
	durat = tg.getDuration()
	if durat:
		tg.markupContent += '<span class="tgduration">Duration: ' + printDuration(durat) + '</span>'
	tg.needsUpdate = True
	tg.save()

	if tgComment != '':
		# if task is TODO or FIXME
		for com in task.comments:
			TaskGroupComment.create(idTaskGroup = tg, content = com)
	else:
		if (task.fullLine, task.lineId) in idsDict:
			tsk = Task.create(id = idsDict[(task.fullLine, task.lineId)][0], content = task.descr, fullLine = task.fullLine, priority = task.prio, state = tskstate, started = task.started, duration = task.duration, parentPage = notePg, group = tg, parent = par, previous = prev, lineId = task.lineId, mostUrgentDate = None, actionable = False, lastMailReminder = idsDict[(task.fullLine, task.lineId)][1])
		else:
			task.printToConsole()
			tsk = Task.create(content = task.descr, fullLine = task.fullLine, priority = task.prio, state = tskstate, started = task.started, duration = task.duration, parentPage = notePg, group = tg, parent = par, previous = prev, lineId = task.lineId, mostUrgentDate = None, actionable = False, lastMailReminder = None)

		tsk.actionable = tsk.isActionable()
		tsk.save()

		# Comments
		for com in task.comments:
			Comment.create(idTask = tsk, content = com)
		
		# Tags
		for tag in task.tags:
			AddTag(tag, tsk)

		# Due dates
		for dd in task.due:
			AddDueDate(dd, tsk)

		# Update user values
		tsk.parentPage.book.user.updateMaxPrio(tsk.priority)

		tsk.markupContent = ParseMarkup(tsk.content, tsk.parentPage, tsk.parentPage.book.url)
		tsk.save()

	# subtasks
	subtsk = None
	for subtask in task.subtasks:
		subtsk = InsertTaskInDb(subtask, tsk, subtsk, notePg, idsDict, tgIdsDict)

	return tsk

def AddDueDate(dd, tsk):
	dateDB = None
	# If the date doesn't belong to a parent task
	if not dd[2]:
		dateDB = DueDate.create(date = dd[0], origDate = dd[0], cycleCounter = 0, cyclic_y = dd[1][0], cyclic_m = dd[1][1], cyclic_d = dd[1][2])
	else:
		dateDB = DueDate.select().join(TaskDates).join(Task).where((Task.id == tsk.parent.id) & (DueDate.date == dd[0]) & (DueDate.cyclic_y == dd[1][0]) & (DueDate.cyclic_m == dd[1][1]) & (DueDate.cyclic_d == dd[1][2])).get()
	if (TaskDates.select().where((TaskDates.from_task == tsk) & (TaskDates.to_date == dateDB)).count() == 0):
		TaskDates.create(from_task = tsk, to_date = dateDB, parentDate = dd[2])
	if not tsk.mostUrgentDate or (tsk.mostUrgentDate.date > dateDB.date):
		tsk.mostUrgentDate = dateDB
		tsk.updatePregenNeeded = True
		tsk.save()

def AddTag(tag, tsk):
	tagDB = None
	try:
		tagDB = Tag.get(Tag.name == tag)
	except:
		tagDB = Tag.create(name = tag, parent = None)
	TaskTags.create(from_task = tsk, to_tag = tagDB)
	tsk.markupTags += unicode(tagDB.html())
	tsk.save()
	tsk.parentPage.book.user.updateSpecifTag(tagDB.id)

tp = None
def PrintAllTasks():
	tp.PrintAllTasks()

def DeleteNoteBook(noteBk):
	# Delete all associated note pages
	for notePg in NotePage.select().where(NotePage.book == noteBk):
		DeleteNotePage(notePg)
	noteBk.user.updatePregenNeeded = True
	noteBk.user.save()
	NoteBook.delete().where(NoteBook.id == noteBk.id).execute()

	#usr.updateTagList()

def DeleteNotePage(notePg):
	# Get all associated tags 
	allTags = Tag.select().join(TaskTags).join(Task).where(Task.parentPage == notePg)
	# update the user tags
	notePg.book.user.removeTagList(allTags)
	# Delete tasks and taskgroups
	tgids = [tmp.group for tmp in Task.select().where(Task.parentPage == notePg)]
	if len(tgids) > 0:
		# Delete taskgroups
		if TaskGroup.select().where(TaskGroup.id << tgids).count() > 0:
			TaskGroup.delete().where(TaskGroup.id << tgids).execute()
		# Delete tasks
		Task.delete().where(Task.parentPage == notePg).execute()
	# CleanUp Dates
	if TaskDates.select().count() > 0:
		if DueDate.select().where(~(DueDate.id << [tmp.to_date for tmp in TaskDates.select()])).count() > 0:
			DueDate.delete().where(~(DueDate.id << [tmp.to_date for tmp in TaskDates.select()])).execute()
	else:
		DueDate.delete().execute()
	# CleanUp Tags
	if TaskTags.select().count() > 0:
		if Tag.select().where(~(Tag.id << [tmp.to_tag for tmp in TaskTags.select()])).count() > 0:
			Tag.delete().where(~(Tag.id << [tmp.to_tag for tmp in TaskTags.select()])).execute()
	else:
		Tag.delete().execute()

def UpdateDB(user, thrLock = None):
	print(id(db.get_conn()))
	changed = False
	with getAtomicLock(thrLock):
		notebooks = [nb for nb in NoteBook.select().where(NoteBook.user == user)]
	
	for notebook in notebooks:
		with getAtomicLock(thrLock):
			print(notebook.name + ' // ' + notebook.path)
			if notebook.useGit:
				notebook.CreateNotebookGitHooks()

		# Parse the note files
		print(u'Start parsing files')
		tp = TaskParser()
		with getAtomicLock(thrLock):
			tp.ParseFile(notebook.path, lambda x:NotePage.select().where((NotePage.book == notebook) & (NotePage.path == x)))
		print(u'End parsing files')

		needToPregenUser = False
		notePg = None
		lastTsk = None
		lastPage = ''
		toAdd = False
		oldTaskIds = {}
		oldTaskGroupIds = {}
		with getAtomicLock(thrLock):
			allPages = Set([pg.path for pg in NotePage.select().where(NotePage.book == notebook)])
		# For each task in all files
		for task in tp.rootTask.subtasks:
			with db.atomic(thrLock):
				if lastPage != task.fileLink:
					notePg = None
					toAdd = False
					oldTaskIds = {}
					if NotePage.select().where((NotePage.book == notebook) & (NotePage.path == task.fileLink)).count() == 0:
						notePg = NotePage.create(path = task.fileLink, lastModif = task.lastModif, lastModifMicroSec = task.lastModif.microsecond, book = notebook)
						toAdd = True
						needToPregenUser = True

					notePg = NotePage.get((NotePage.path == task.fileLink) & (NotePage.book == notebook));
					if ((notePg.lastModif < task.lastModif.replace(microsecond=0)) or ((notePg.lastModif == task.lastModif.replace(microsecond=0)) and (notePg.lastModifMicroSec < task.lastModif.microsecond))):
						# save tasks ids
						oldTaskIds = {(tsk.fullLine, tsk.lineId): (tsk.id, tsk.lastMailReminder) for tsk in notePg.tasksinpage}
						oldTaskGroupIds = {tg.name : tg.id for tg in notePg.getTaskGroups()}
						# delete everything related to this page
						DeleteNotePage(notePg)
						# update page
						notePg.lastModif = task.lastModif
						notePg.lastModifMicroSec = task.lastModif.microsecond
						notePg.save()
						# add current task
						toAdd = True
					lastPage = task.fileLink

				if toAdd:
					changed = True
					lastTsk = InsertTaskInDb(task, None, lastTsk, notePg, idsDict = oldTaskIds, tgIdsDict = oldTaskGroupIds)

		# Remove orphan tasks
		with getAtomicLock(thrLock):
			for pgName in allPages:
				if pgName not in tp.allPages:
					changed = True
					needToPregenUser = True
					npg = NotePage.get((NotePage.path == pgName) & (NotePage.book == notebook))
					DeleteNotePage(npg)
					# Delete the note page itself
					NotePage.delete().where(NotePage.id == npg.id).execute()

			# Update the pregenerated content for user
			if needToPregenUser:
				User.get(User.login == user.login).generatePreGen()

	return changed

from UpdateDB import runUpdate
