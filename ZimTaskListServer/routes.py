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
from flask import Flask, render_template, request, session, redirect
from markdown import markdown
from TaskToDB import *
import logging
from Parameters import *
from PageManager import *
import subprocess
from scheduleTasks import UpdateCronTab, dummyPgMngr
from math import log
import threading
from UpdateDaemon import updateLoop, updatePreGens

import traceback

from werkzeug.contrib.profiler import ProfilerMiddleware

app = Flask(__name__)      
file_handler = logging.FileHandler(filename=flaskLogPath)
file_handler.setLevel(logging.WARNING)
app.logger.addHandler(file_handler)

# Profiler
f = open('/tmp/profiler.log', 'a')
app.wsgi_app = ProfilerMiddleware(app.wsgi_app, f, sort_by=['cumtime'], profile_dir='/tmp/pstats')

try:
	app.secret_key = App.get().secretKey
except:
	app.secret_key = '\x01\x19H#L\xe8\r\xb6\xb83\x8c\xfa\xbaq\xa9T-\xeb\xee\x8c\xc9\xf1o\x1e'

app.threadLock = threading.Lock()

globPageMngr = PageManager()
 
@app.route('/', methods=['GET', 'POST'])
def homepage():
	if dbType == 'MySQL':
		db.get_conn().ping(True)

	if 'chckboxState' not in session:
		session['chckboxState'] = 1
	if 'groupbyState' not in session:
		session['groupbyState'] = 'none'
	if 'orderbyList' not in session:
		session['orderbyList'] = ['none']
	if 'tagfilterlist' not in session:
		session['tagfilterlist'] = ['-']
	if 'searchFilt' not in session:
		session['searchFilt'] = ''
	if 'login' not in session:
		session['login'] = ''
	if 'ErrorMsg' not in session:
		session['ErrorMsg'] = ''
	if 'ConfirmationMsg' not in session:
		session['ConfirmationMsg'] = ''
	if 'TechnicalMsg' not in session:
		session['TechnicalMsg'] = ''
	if 'prevOp' not in session:
		session['prevOp'] = ''
	
	with getAtomicLock(app.threadLock):
		if App.get().nologin:
			session['login'] = 'admin'

		with db.atomic(app.threadLock) as transact:
			if request.method == 'POST':
				if request.form.get('loginBtn'):
					login = request.form.get('loginField')
					if (login in [u.login for u in User.select(User.login)]) and User.get(User.login == login).check_password(request.form.get('passwordField')):
						session['login'] = login
					else:
						session['ErrorMsg'] = 'Invalid login or password'
					return redirect(url_for('homepage'))

			if session['login'] in [u.login for u in User.select(User.login)]:
				if request.method == 'POST':
					if request.form.get('chckboxcontent'):
						session['chckboxState'] = int(request.form['chckboxcontent']) % 4
						if request.form.get('groupbydropdown'):
							session['groupbyState'] = 'taskgroup'
						else:
							session['groupbyState'] = 'none'

					for i in range(len(session['orderbyList'])):
						if request.form.get('orderby'+str(i)):
							session['orderbyList'][i] = request.form['orderby'+str(i)]
					for i in range(len(session['tagfilterlist'])):
						if request.form.get('tagfilter'+str(i)):
							session['tagfilterlist'][i] = request.form['tagfilter'+str(i)]
					for tag in Tag.select():
						if request.form.get(tag.name) and not (tag.name in session['tagfilterlist']):
							session['tagfilterlist'][-1] = request.form[tag.name]
							session['searchFilt'] = ''
					if request.form.get('ClearButton'):
						session['tagfilterlist'] = ['-']
					if request.form.get('ClearButtonOrderBy'):
						session['orderbyList'] = ['none']

					if request.form.get('StartButton'):
						m = re.compile('start_([0-9]+)_([0-9]+)').match(request.form['StartButton'])
						try:
							task = Task.get(Task.id == int(m.group(1)))
							task.updateStarted(int(m.group(2)))
						except:
							session['ErrorMsg'] = 'There was an issue for starting the task. Please try again.'
					if request.form.get('AddCommentBtn'):
						try:
							task = Task.get(Task.id == int(request.form['AddCommentBtn']))
							task.addComment(request.form['CommentText'])
						except:
							session['ErrorMsg'] = 'There was an issue while adding your comment, please try again : ' + request.form['CommentText']
					if request.form.get('StatusButton') or request.form.get('CancelButton'):
						p = re.compile('status([0-9]+)_([0-9]+)')
						m = p.match(request.form['StatusButton']) if request.form.get('StatusButton') else p.match(request.form['CancelButton'])
						taskId = int(m.group(1))
						state = int(m.group(2))
						try:
							task = Task.get(Task.id == taskId)
							task.updateState(state)
						except Exception, e:
							session['ErrorMsg'] = 'Changing the state of the task did not work. Please try again.'
							session['TechnicalMsg'] = str(e)
					if request.form.get('TaskGroupStatusButton'):
						p = re.compile('status([0-9]+)_([0-9]+)')
						m = p.match(request.form['TaskGroupStatusButton'])
						taskgroupId = int(m.group(1))
						state = int(m.group(2))
						try:
							taskgroup = TaskGroup.get(TaskGroup.id == taskgroupId)
							taskgroup.updateState(state)
						except:
							session['ErrorMsg'] = 'Changing the state of the task group did not work. Please try again.'
					if request.form.get('AddTaskBtn'):
						req = request.form.get('AddTaskBtn')
						newId = None
						child = False
						if 'norm' in req:
							taskId = int(req[4:])
						elif 'sub' in req:
							taskId = int(req[3:])
							child = True
						text = request.form.get('AddTaskText')
						taskTarget = None
						if taskId == -1:
							notePgId = int(request.form.get('notepgselect'))
							if NotePage.select().where(NotePage.id == notePgId).count() > 0:
								try:
									newId = NotePage.get(NotePage.id == notePgId).addTask(text)
								except Exception, e:
									session['ErrorMsg'] = 'Adding the task failed, please try again: ' + text
									session['TechnicalMsg'] = str(e)
							else:
								session['ErrorMsg'] = 'Could not find the note page to add the task, please try again: ' + text
						else:
							if Task.select().where(Task.id == taskId).count() > 0:
								try:
									newId = Task.get(Task.id == taskId).addTask(text, child)
								except Exception, e:
									session['ErrorMsg'] = 'Adding the task failed, please try again: ' + text
									session['TechnicalMsg'] = str(e)
							else:
								session['ErrorMsg'] = 'Could not find the base task for adding the task, please try again : ' + text
						if newId is not None:
							session['prevOp'] = 'AddTask' + str(newId)
					if request.form.get('AddTaskGroupBtn'):
						req = request.form.get('AddTaskGroupBtn')
						below = False
						newId = None
						if 'tgbelow' in req:
							taskGrId = int(req[7:])
							below = True
						elif 'tgabove' in req:
							taskGrId = int(req[7:])
						tgType = request.form.get('TaskGroupType')
						tgText = request.form.get('AddTaskGroupDescr')
						tskText = request.form.get('AddTaskGroupText')
						tgTarget = None
						if taskGrId == -1:
							notePgId = int(request.form.get('notepgselect'))
							if NotePage.select().where(NotePage.id == notePgId).count() > 0:
								try:
									newId = NotePage.get(NotePage.id == notePgId).addTaskGroup(tgType, tgText, tskText)
								except Exception, e:
									session['ErrorMsg'] = 'Adding the taskgroup failed, please try again: ' + tgText + ' / ' + tskText + ' (' + str(e) + ')'
							else:
								session['ErrorMsg'] = 'Could not find the note page to add the taskgroup, please try again: ' + tgText + ' / ' + tskText
						else:
							if TaskGroup.select().where(TaskGroup.id == taskGrId).count() > 0:
								try:
									newId = TaskGroup.get(TaskGroup.id == taskGrId).addTaskGroup(tgType, tgText, tskText, below)
								except Exception, e:
									session['ErrorMsg'] = 'Adding the taskgroup failed, please try again: ' + tgText + ' / ' + tskText + ' (' + str(e) + ')'
							else:
								session['ErrorMsg'] = 'Could not find the base taskgroup for adding the taskgroup, please try again: ' + tgText + ' / ' + tskText
						if newId is not None:
							session['prevOp'] = 'AddTask' + str(newId)
					try:
						session['searchFilt'] = request.form['SearchBar']
						globPageMngr.CheckRegExp()
					except:
						pass
					# Redirect after a post request
					return redirect(url_for('homepage'))
				# Normal page displaying
				else:
					globPageMngr.UpdateTagFilter()
					with db.atomic(app.threadLock):
						user = User.get(User.login == session['login'])
						querryResult = globPageMngr.GetQuerry()
						if session['groupbyState'] == 'taskgroup':
							genPage = render_template('homepage.html', taskgroups = querryResult, Task=Task, pageMngr = globPageMngr, ErrorMsg=session['ErrorMsg'], TechnicalMsg=session['TechnicalMsg'], user = user, colorHighPrio = user.colorHighPrio, colorLowPrio = user.colorLowPrio, maxPrio = user.maxPrio, appli = App.get())
						else:
							genPage = render_template('homepage.html', tasks = querryResult , pageMngr = globPageMngr, ErrorMsg=session['ErrorMsg'], TechnicalMsg=session['TechnicalMsg'], user = user, colorHighPrio = user.colorHighPrio, colorLowPrio = user.colorLowPrio, maxPrio = user.maxPrio, appli = App.get())
			else:
				genPage = render_template('login.html', ErrorMsg = session['ErrorMsg'], ConfirmationMsg = session['ConfirmationMsg'], appli=App.get())

			session['ErrorMsg'] = ''
			session['ConfirmationMsg'] = ''
			session['TechnicalMsg'] = ''
			session['prevOp'] = ''

			return genPage

@app.route('/Preferences', methods=['GET', 'POST'])
def preferences():
	fakePwd = 'dojqopdifjefnygd'
	if 'ErrorMsg' not in session:
		session['ErrorMsg'] = ''
	if 'ConfirmationMsg' not in session:
		session['ConfirmationMsg'] = ''
	if 'TechnicalMsg' not in session:
		session['TechnicalMsg'] = ''

	if dbType == 'MySQL':
		db.get_conn().ping(True)
	with db.atomic(app.threadLock):
		if ('login' in session) and (session['login'] in [u.login for u in User.select(User.login)]):
			user = User.get(User.login == session['login'])
			if request.method == 'POST':
				if request.form.get('UpdateCommonBtn'):
					if request.form.get('passwordField') != fakePwd:
						try:
							user.hash_pwd = generate_password_hash(request.form.get('passwordField'))
							user.save()
							session['ConfirmationMsg'] += 'Password updated successfully. '
						except Exception, e:
							session['ErrorMsg'] += 'Could not update the password. '
							session['TechnicalMsg'] += str(e)
					if request.form.get('cssTheme'):
						try:
							user.SetCss(request.form.get('cssTheme'))
							session['ConfirmationMsg'] += 'Theme updated successfully. '
						except Exception, e:
							session['ErrorMsg'] += 'Could not update the theme. '
							session['TechnicalMsg'] += str(e)

				if request.form.get('UpdateCalendarBtn'):
					try:
						if request.form.get('calEnable'):
							user.calEnable = True
						else:
							user.calEnable = False
						user.calURL = unicode(request.form.get('calURL'))
						user.calUsrName = request.form.get('calUsrName')
						if request.form.get('calPwd') != fakePwd:
							user.calPwd = request.form.get('calPwd')
						user.save()
						# Check that they work
						try:
							ctm = CalendarTaskManager(user)
							if user.calEnable:
								ctm.UpdateCalendar()
							session['ConfirmationMsg'] = 'Calendar parameters updated.'
						except Exception, e:
							session['ErrorMsg'] = 'The supplied parameters are not correct.'
							session['TechnicalMsg'] = str(e)
							user.calEnable = False
							user.save()
					except Exception, e:
						session['ErrorMsg'] = 'Could not update the calendar parameters.'
						session['TechnicalMsg'] = str(e)

				if request.form.get('UpdateMailBtn'):
					try:
						if request.form.get('mailEnable'):
							user.mailEnable = True
						else:
							user.mailEnable = False
						user.mailDays = request.form.get('mailDays')
						user.mailTimes = request.form.get('mailTimes')
						user.mailCategories = unicode(request.form.get('mailCategories'))
						user.mailAddress = unicode(request.form.get('mailAddress'))
						user.mailSubject = request.form.get('mailSubject')
						user.save()
						session['ConfirmationMsg'] = 'Mail reminder parameters updated.'
					except Exception, e:
						session['ErrorMsg'] = 'Could not update the mail reminder parameters.'
						session['TechnicalMsg'] = str(e)

				if request.form.get('RemoveNotebook'):
					try:
						nbInd = int(request.form.get('RemoveNotebook'))
						notebook = NoteBook.get(NoteBook.id == nbInd)
						notebook.RemoveNotebookGitHooks()
						DeleteNoteBook(notebook)
						session['ConfirmationMsg'] += 'Notebook deleted.'
					except Exception, e:
						session['ErrorMsg'] += 'Could not delete notebook.'
						session['TechnicalMsg'] += str(e)

				if request.form.get('UpdateNotebooksBtn'):
					for notebook in user.notebooks:
						if request.form.get('NoteBooksName_' + str(notebook.id)):
							try:
								notebook.name = request.form.get('NoteBooksName_' + str(notebook.id))
								notebook.path = request.form.get('NoteBooksPath_' + str(notebook.id))
								notebook.rootPath = request.form.get('NoteBooksRootPath_' + str(notebook.id))
								notebook.url = request.form.get('NoteBooksURL_' + str(notebook.id))
								notebook.useGit = True if request.form.get('UseGit_' + str(notebook.id)) else False
								notebook.repoPath = request.form.get('NoteBooksGitRepo_' + str(notebook.id))
								notebook.save()
								notebook.CreateNotebookGitHooks()
								notebook.UpdateTaskPregen()
								session['ConfirmationMsg'] += notebook.name + ' updated. '
							except Exception, e:
								session['ErrorMsg'] += notebook.name + ' failed updating.'
								session['TechnicalMsg'] += str(e) + '\n'
					if (request.form.get('NoteBooksName') != '') or (request.form.get('NoteBooksPath') != '') or (request.form.get('NoteBooksRootPath') != ''):
						if (request.form.get('NoteBooksName') != '') and (request.form.get('NoteBooksPath') != '') and (request.form.get('NoteBooksRootPath') != ''):
							try:
								NoteBooksName = request.form.get('NoteBooksName').split(',')
								NoteBooksPath = request.form.get('NoteBooksPath').split(',')
								NoteBooksRootPath = request.form.get('NoteBooksRootPath').split(',')
								NoteBooksURL = request.form.get('NoteBooksURL').split(',')
								useGit = True if request.form.get('UseGit') else False
								NoteBooksGitRepo = request.form.get('NoteBooksGitRepo').split(',')
								for i in range(len(NoteBooksPath)):
									if NoteBook.select().where((NoteBook.path == NoteBooksPath[i]) & (NoteBook.user == user)).count() == 0:
										user.addNotebook(name = NoteBooksName[i], path = NoteBooksPath[i], rootPath = NoteBooksRootPath[i], url = NoteBooksURL[i], useGit = useGit, repoPath = NoteBooksGitRepo[i])
								UpdateCronTab(user)
								UpdateDB(user)
								session['ConfirmationMsg'] = 'Notebook added.'
							except Exception, e:
								session['ErrorMsg'] = 'Could not add notebook.'
								session['TechnicalMsg'] = str(e)
								session['TechnicalMsg'] += Markup('<br>' + traceback.format_exc().replace('\n', '<br>'))
						else:
							session['ErrorMsg'] = 'The fields Name, Path and Root Path must be provided in order to add a new notebook.'

				return redirect(url_for('preferences'))

			pageGen = render_template('preferences.html', logged = True, ErrorMsg = session['ErrorMsg'], ConfirmationMsg = session['ConfirmationMsg'], TechnicalMsg = session['TechnicalMsg'], user = user, fakePwd = fakePwd)
		else:
			pageGen = render_template('login.html', ErrorMsg = session['ErrorMsg'], ConfirmationMsg = session['ConfirmationMsg'], appli=App.get())
	session['ErrorMsg'] = ''
	session['ConfirmationMsg'] = ''
	session['TechnicalMsg'] = ''
	return pageGen

@app.route('/CreateUser', methods=['GET', 'POST'])
def createuser():
	if 'ErrorMsg' not in session:
		session['ErrorMsg'] = ''
	if 'ConfirmationMsg' not in session:
		session['ConfirmationMsg'] = ''
	if 'TechnicalMsg' not in session:
		session['TechnicalMsg'] = ''
	login = ''
	if dbType == 'MySQL':
		db.get_conn().ping(True)
	with db.transaction():
		appli = App.get()
		user = None
		if ('login' in session) and (session['login'] in [u.login for u in User.select(User.login)]):
			user = User.get(User.login == session['login'])
		if appli.allowUserCreation or (user is not None and user.isAdmin):
			if request.method == 'POST':
				if request.form.get('createUserBtn'):
					# TODO write special code for verifying users ?
					session['ConfirmationMsg'], session['ErrorMsg'], session['TechnicalMsg'], login = HandleUserCreation(request)
				return redirect(url_for('createuser'))
			pageGen = render_template('CreateUser.html', logged = True, ErrorMsg = session['ErrorMsg'], ConfirmationMsg = session['ConfirmationMsg'], TechnicalMsg = session['TechnicalMsg'], loginVal = login, appli = appli)
		else:
			session['ErrorMsg'] = 'You need to be logged in as an adminitrator to create new users.'
			pageGen = render_template('CreateUser.html', logged = False, ErrorMsg = session['ErrorMsg'], ConfirmationMsg = session['ConfirmationMsg'], TechnicalMsg = session['TechnicalMsg'], loginVal = '', appli = appli)

	
	session['ErrorMsg'] = ''
	session['ConfirmationMsg'] = ''
	session['TechnicalMsg'] = ''
	return pageGen

def HandleUserCreation(request):
	login = request.form.get('loginField')
	pwd = request.form.get('passwordField')
	pwdVerif = request.form.get('passwordFieldVerif')
	ErrorMsg = ''
	ConfirmationMsg = ''
	TechnicalMsg = ''
	if User.select().where(User.login == login).count() > 0:
		ErrorMsg = 'Your login is already in use.'
		login = ''
	else:
		if pwd == '':
			ErrorMsg = 'Password is empty !'
		else:
			if pwd == pwdVerif:
				try:
					User.create(login = login, hash_pwd = generate_password_hash(pwd), isAdmin = False)
					ConfirmationMsg = 'User created successfully.'
				except Exception, e:
					ErrorMsg = 'User creation failed.'
					TechnicalMsg = str(e)
			else:
				ErrorMsg = 'Passwords do not match.'
	return (ConfirmationMsg, ErrorMsg, TechnicalMsg, login)

@app.route('/Admin', methods=['GET', 'POST'])
def admin():
	login = ''
	if 'ErrorMsg' not in session:
		session['ErrorMsg'] = ''
	if 'ConfirmationMsg' not in session:
		session['ConfirmationMsg'] = ''
	if 'TechnicalMsg' not in session:
		session['TechnicalMsg'] = ''

	if dbType == 'MySQL':
		db.get_conn().ping(True)
	with db.atomic(app.threadLock):
		appli = App.get()
		if ('login' in session) and (session['login'] in [u.login for u in User.select(User.login)]):
			user = User.get(User.login == session['login'])
			if user.isAdmin:
				if request.method == 'POST':
					if request.form.get('UpdateApplicationBtn'):
						try:
							if request.form.get('allowUserCreation'):
								appli.allowUserCreation = True
							else:
								appli.allowUserCreation = False
							if request.form.get('nologinchckbox'):
								appli.nologin = True
							else:
								appli.nologin = False
							appli.localUpdatePeriod = int(request.form.get('localUpdatePeriod'))
							appli.mailSenderAddress = request.form.get('mailSenderAddress')
							appli.mailSendMailPath = request.form.get('mailSendMailPath')
							appli.cssTheme = request.form.get('cssTheme')
							appli.save()
							session['ConfirmationMsg'] = 'Parameters updated.'
						except Exception, e:
							session['ErrorMsg'] = 'An issue occured while updating the parameters.'
							session['TechnicalMsg'] = str(e)
					if request.form.get('createUserBtn'):
						# TODO write special code for verifying users ?
						session['ConfirmationMsg'], session['ErrorMsg'], session['TechnicalMsg'], login = HandleUserCreation(request)
					if request.form.get('DeleteUserBtn'):
						try:
							usrId = int(request.form.get('DeleteUserBtn'))
							tmpUsr = User.get(User.id == usrId)
							for nbk in tmpUsr.notebooks:
								for npg in nbk.notePages:
									DeleteNotePage(npg)
								nbk.RemoveNotebookGitHooks()
							User.delete().where(User.id == usrId).execute()
							session['ConfirmationMsg'] = 'User deleted successfully.'
						except Exception, e:
							session['ErrorMsg'] = 'Could not delete the user.'
							session['TechnicalMsg'] = str(e)

					return redirect(url_for('admin'))

				pageGen = render_template('Admin.html', logged = True, ErrorMsg = session['ErrorMsg'], ConfirmationMsg = session['ConfirmationMsg'], TechnicalMsg = session['TechnicalMsg'], appli = appli, loginVal = login, user = user)
			else:
				session['ErrorMsg'] = 'You are not logged in as an administrator.'
				pageGen = render_template('Admin.html', logged = False, ErrorMsg = session['ErrorMsg'], ConfirmationMsg = session['ConfirmationMsg'], TechnicalMsg = session['TechnicalMsg'], appli = appli, loginVal = login, user = user)
		else:
			session['ErrorMsg'] = 'You are not logged in.'
			pageGen = render_template('Admin.html', logged = False, ErrorMsg = session['ErrorMsg'], ConfirmationMsg = session['ConfirmationMsg'], appli = appli, loginVal = login, user = appli)
	
	session['ErrorMsg'] = ''
	session['ConfirmationMsg'] = ''
	session['TechnicalMsg'] = ''
	return pageGen

@app.route('/Logout', methods=['GET', 'POST'])
def logout():
	session['login'] = ''
	return redirect(url_for('homepage'))


# If local use
if App.get().nologin:
	thr = threading.Thread(target = updateLoop, args = (app.threadLock,))
	thr.daemon = True
	thr.start()
# Generate pregens as a background task
preGenThr = threading.Thread(target = updatePreGens, args = (app.threadLock,))
preGenThr.daemon = True
preGenThr.start()

if __name__ == '__main__':

	app.run(debug=True, use_reloader=False)

from CalendarSync import CalendarTaskManager
