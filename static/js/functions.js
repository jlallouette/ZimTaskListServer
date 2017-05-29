function goToByScroll(id){
	if (Math.abs($(window).scrollTop() + $(window).height() / 2 - $(id).offset().top) > $(window).height() / 3) {
		$('html,body').animate({
			scrollTop: $(id).offset().top - $(window).height() / 2},
			'slow');
	}
}

var chkList = {
	"nologinchckbox":{
		"on":["localUpdatePeriod"], 
		"off":["allowUserCreation", "mailSenderAddress", "mailSendMailPath", "cssTheme"]},
	"calEnable":{
		"on":["calURL", "calUsrName", "calPwd"],
		"off":[]},
	"mailEnable":{
		"on":["mailAddress", "mailSubject", "mailDays", "mailTimes", "mailCategories"],
		"off":[]},
	"UseGit":{
		"on":["NoteBooksGitRepo"],
		"off":[]}
};

$(function() {
	$('.stdChkBx').click(
		function() {
			var name = $(this).attr('name');
			for (var key in chkList) {
				var rg = new RegExp('^(' + key + ')(_[0-9]+)?');
				if (rg.test(name)) {
					var checked = $(this).is(":checked")
					rg.lastIndex = 0;
					var tmp = rg.exec(name);
					for (var i = 0 ; i < chkList[key]["on"].length ; i++) {
						var name2 = chkList[key]["on"][i];
						if (tmp[2]) {
							name2 = name2 + tmp[2]
						}
						if (checked) {
							$('[name=' + name2 + ']').parent().attr('style', 'display:table-row;');
						} else {
							$('[name=' + name2 + ']').parent().hide();
						}
					}
					for (var i = 0 ; i < chkList[key]["off"].length ; i++) {
						var name2 = chkList[key]["off"][i];
						if (tmp[2]) {
							name2 = name2 + tmp[2]
						}
						if (!checked) {
							$('[name=' + name2 + ']').parent().attr('style', 'display:table-row;');
						} else {
							$('[name=' + name2 + ']').parent().hide();
						}
					}
				}
			}
		}
	);
	$('.CloseButton').click(
		function() {
			var name = $(this).attr('id');
			$('#Comment'+name).hide();
			$('#AddTask'+name).hide();
			$('#SubTask'+name).hide();
			$('#AddSubTask'+name).hide();
		}
	);
	$('.CloseButtonTg').click(
		function() {
			var name = $(this).attr('id');
			$('#AddTaskGroup'+name).hide();
		}
	);
	$('.AddCommButton').click(
		function() {
			$("[id^=Comment]").hide()
			$("[id^=AddTask]").hide()
			$("[id^=SubTask]").hide()
			$("[id^=AddSubTask]").hide()
			$("[id^=AddTaskGroup]").hide()

			var name = $(this).attr('id');
			$('#Comment'+name).slideToggle("fast");
			$('#'+name+'.AddComText').focus();
		}
	);
	$('.AddTaskButton').click(
		function() {
			$("[id^=Comment]").hide()
			$("[id^=AddTask]").hide()
			$("[id^=SubTask]").hide()
			$("[id^=AddSubTask]").hide()
			$("[id^=AddTaskGroup]").hide()

			var name = $(this).attr('id');
			$('#AddTask'+name).slideToggle("fast");
			goToByScroll("#AddTask"+name);
			$('#norm_'+name+'.AddTaskText').focus();
		}
	);
	$('.AddSubTaskButton').click(
		function() {
			$("[id^=Comment]").hide()
			$("[id^=AddTask]").hide()
			$("[id^=SubTask]").hide()
			$("[id^=AddSubTask]").hide()
			$("[id^=AddTaskGroup]").hide()

			var name = $(this).attr('id');
			$('#SubTask'+name).slideToggle("fast");
			$('#AddSubTask'+name).slideToggle("fast");
			goToByScroll("#AddSubTask"+name);
			$('#sub_'+name+'.AddTaskText').focus();
		}
	);
	$('.AddTaskGroupButton').click(
		function() {
			$("[id^=Comment]").hide()
			$("[id^=AddTask]").hide()
			$("[id^=SubTask]").hide()
			$("[id^=AddSubTask]").hide()
			$("[id^=AddTaskGroup]").hide()

			var name = $(this).attr('id');
			$('#AddTaskGroup'+name).slideToggle("fast");

			goToByScroll("#AddTaskGroup"+name);
			$('#taskgroupText'+name+'.AddTaskGroupText').focus();
		}
	);
	$('.CalendarButton').click(
		function() {
			var name = $(this).attr('id');
			$(this).datepicker("dialog", "onSelect", function(datetext2, pickerinst) {
				var currentDate = new Date(datetext2);
				var datetext = $.datepicker.formatDate("' [d: 'yy-mm-dd'] '", currentDate);
				var target = 'input#' + name;
				$(target).val($(target).val() + datetext);
			});
		}
	);
	$('.TagCloudButton').click(
		function() {
			var name = $(this).attr('id');
			$('#TagDialogBox').dialog("open");
			$('#TagDialogBox').attr("specialId", name);
		}
	);
	$('#ShowTagCloudFilter').click(
		function() {
			$('#TagFilterCloud').slideToggle("fast");
		}
	);
	$('html').click(
		function() {
			$('#TagFilterCloud').hide();
		}
	);
	$('.TagFilterControl').on('click',
		function(evt) {
			if($('#TagFilterCloud').is(":visible")) {
				evt.stopPropagation();
			}
		}
	);
			
	$('#TagDialogBox').dialog({autoOpen: false});
	$('#TagDialogBox form button').on('click',
		function(evt) {
			evt.preventDefault();
			var tagContent = ' ' + $(this).val() + ' ';
			var name = $('#TagDialogBox').attr("specialId");
			var target = 'input#' + name;
			$(target).val($(target).val() + tagContent);
		}
	);

	$('.LoadingButton,.AddTaskBtn,.AddTaskGroupBtn').click(
		function() {
			$(this).html('<img src="static/img/loading.gif" style="width:32px;height:32px;"/>')
		}
	);
});
