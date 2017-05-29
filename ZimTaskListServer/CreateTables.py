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
from peewee import *
from Parameters import *
from TaskToDB import *

def create_tables():
	with db.atomic():
		db.create_tables([TaskGroup, Tag, Task, Comment, DueDate, TaskDates, TaskTags, TaskGroupComment, NotePage, NoteBook, User, App])
		App.create(secretKey = os.urandom(DEFAULT_SECRETKEY_LEN), mailSenderAddress = mailSenderAddress, mailSendMailPath = mailSendMailPath, allowUserCreation = allowUserCreation, nologin = NoLogin, localUpdatePeriod = localUpdatePeriod)
		User.create(login = 'admin', hash_pwd = generate_password_hash('admin'), isAdmin = True)

if __name__ == "__main__":
	create_tables()
