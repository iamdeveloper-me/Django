import re
import pickle
import base64
import datetime
import calendar

from django.db import models, connection, transaction
from django.db.models import Q
from django.utils.datastructures import SortedDict
from django.contrib.auth.models import User
from django.utils.text import wrap
from django.db.models.signals import post_save, pre_save, pre_delete
from django.contrib.contenttypes import generic

from pursuits.timezones.fields import LocalizedDateTimeField
from pursuits.general.models import Note, UserAddedBy
from pursuits.utils import (make_choice, title_to_code, PursuitsManager,
                    post_save_notes_signal, create_timeline_item,
                    get_current_user, date_or_today, get_sandbox,
                    month_bounds, post_save_document_signal,
                    email_notify, get_root_website_url, is_admin,
                    insert_url_elements_into_text, cache)
from pursuits.defaults import (DatabaseInconsistency, REMINDER_TYPES,
        TodoError, MONTHLY_DETAILED_VIEW, MONTHLY_SUMMARY_VIEW,
        RECUR_MAX_DAYS_CREATE_TODOS, TodoRecurrenceError,
        FIRST_WEEKDAY, RECUR_MAX_TODOS, TODO_TASK_TYPES,
        STANDARD_EMAIL_FOOTER, SandboxError)


DELEGATED_TODO_DELETED_MSG = u"""
Hello %(USER)s,

%(SENDER)s has just deleted the following To-Do that was monitored:

To-Do : %(TODO)s%(DETAILS)s

===========================================================
%(FOOTER)s
"""

DELEGATED_TODO_ASSIGNED_MSG = u"""
Hello %(USER)s,

%(SENDER)s has just delegated the following To-Do to you:

To-Do : %(TODO)s%(DETAILS)s

===========================================================
You may view the To-Do by going to this page:
%(REFERER)s

%(FOOTER)s
"""

CHANGED_TODO_NOTIFY = u"""
Hello %(USER)s,

%(SENDER)s has just marked the following To-Do as %(STATUS)s:

To-Do : %(TODO)s%(DETAILS)s

%(UPDATE_TODO_NOTIFY)s
===========================================================

You may view the To-Do by going to this page:
%(REFERER)s

%(FOOTER)s
"""

UPDATE_TODO_NOTIFY = u""" 
===========================================================
List of changes:

%(CHANGES)s

"""

TOTAL_DURATION_FORMAT = u'%s Hour(s) and %s Minute(s)'

TODO_REPEATED_UNTIL_FORMAT = u'rtimes:[%s] rdate:[%s]'

# map weekday names according to day number of Python's calendar module
WEEKDAY_NAME_MAPPER = {'Sunday': 6,
                       'Monday': 0,
                       'Tuesday': 1,
                       'Wednesday': 2,
                       'Thursday': 3,
                       'Friday': 4,
                       'Saturday': 5 }

RECURRENCE_TODO_FIELDS = ("sandbox",
                          "creator",
                          "details",
                          "duration",
                          "owner",
                          "name",
                          "due_date_time",
                          "priority",
                          "all_day_event",
                          "time",
                          "task_type",
                          "tough_one",
                          "private",
                          "task_analysis",
                          "calendar_event",
                          "display_time_as")

TODO_OWNER_CHOICES_TIMEOUT = 5 * 60

#
# Helpers
#


class TodoCalendarItem(object):
    def __init__(self, todo):
        self.todo = todo
        # defines whether this is the first to-do in a line or not
        #
        # we only show name and time of multi-day
        # todos that are the first ones in a month line
        self.first_multi_day = False

        # defines whether or not this is the last guy
        # of a multi-day sequence
        self.last_multi_day = False

    @property
    def fake_item(self):
        return self.todo.id is None

    def __repr__(self):
        return u"Todo[%s]: %s" % (self.todo.id, self.todo.name)


def fetch_todos_for_monthly_view(request, user, year, month, day):
    from pursuits.todos.search import mark_private
    def _get_other_month(current_month, current_year, last_month=True):
        if last_month:
            if (current_month - 1) < 1:
                current_year -= 1
                return 12, current_year
            return current_month -1, current_year

        if (current_month + 1) > 12:
            current_year += 1
            return 1, current_year
        return current_month + 1, current_year

    def sort_by_name_cmp(x, y):
        return cmp(x.name.lower(), y.name.lower())

    # make this calendar consistent with the javascript calendar widget
    # each calendar week starts on Sunday
    calendar.setfirstweekday(FIRST_WEEKDAY)

    sandbox = get_sandbox()
    date = date_or_today(year,month,day)
    profile = request.user.get_profile()
    monthstart, monthend = month_bounds(date)
    monthdates = calendar.monthcalendar(monthstart.year, monthstart.month)

    monthdays = []
    multiday_dict = {}
    multiday_todo_dict = {}
    mview = profile.preferred_todo_monthly_view
    for monthline in monthdates:
        monthl = []
        pos = -1
        for monthday in monthline:
            day = {}
            pos += 1
            if monthday == 0:
                is_last_month = monthline[0] == 0
                lmonth, lyear = _get_other_month(monthstart.month,
                                                monthstart.year,
                                                last_month=is_last_month)

                last_month_calendar = calendar.monthcalendar(
                                                    lyear, lmonth)

                last_month_index = -1 if is_last_month else 0
                last_month_week = last_month_calendar[last_month_index]
                last_month_valid_days = [d for d in last_month_week
                                                            if d > 0]

                last_index = 0
                for i in monthline:
                    if i  == 0:
                        last_index += 1

                current_week = [d for d in monthline if d > 0]

                if is_last_month:
                    full_week = last_month_valid_days[
                                                -last_index:] + current_week
                else:
                    full_week = current_week + last_month_valid_days[
                                                            :last_index]
                n_monthday = full_week[pos]
            else:
                n_monthday = monthday
                lmonth, lyear = date.month, date.year

            day["daynum"] = n_monthday
            day["month_num"] = lmonth
            day["year_num"] = lyear
            day["orig_month_day"] = monthday
            day["date"] = datetime.date(lyear, lmonth, n_monthday)

            filter_kwargs = {'owner': user} if user else {}
            date_query = Q(date__lte=day["date"], due_date__gte=day["date"])
            date_query |= Q(date=day["date"], due_date__isnull=True)
            todos = Todo.objects.filter(date_query, sandbox=sandbox,
                **filter_kwargs).order_by(
                    '-all_day_event', 'time', 'name')

            if mview == MONTHLY_DETAILED_VIEW:
                todos = todos.filter(calendar_event=True,
                                     status__in=("Active", "Completed"))
                todos = [t for t in todos
                            if t.time or t.all_day_event]
            else:
                todos = todos.filter(status="Active")

            multiday = [t for t in todos if t.multiday_event]

            previous_day = [t.todo for t in multiday_dict.get(
                    day["date"] - datetime.timedelta(days=1), [])
                    ] if pos > 0 else []

            final_multiday = [
                    t for t in multiday if t.all_day_event] + [
                    t for t in multiday if not t.all_day_event]
            final_multiday_sorted = []

            has_from_previous_day = False
            # bring multi-day from previous day, if we have any
            for item in previous_day:
                if item not in final_multiday:
                    final_multiday_sorted.append(
                                    TodoCalendarItem(Todo())
                                    )
                    continue

                # we have to-dos in this day that are also available
                # in the previous day
                has_from_previous_day = True

                final_multiday.remove(item)
                item_index = previous_day.index(item)

                final_multiday_sorted.insert(item_index,
                            TodoCalendarItem(item)
                            )

            if not has_from_previous_day:
                # If I don't have anything from previous day
                # remove all empty to-dos
                for item in final_multiday_sorted[:]:
                    if item.fake_item:
                        final_multiday_sorted.remove(item)

            for todo in final_multiday:
                final_multiday_sorted.append(
                        TodoCalendarItem(todo))

            # check if there are any new multi-day event and move it to an
            # an empty spot
            fake_items = [i for i in final_multiday_sorted
                            if i.fake_item]
            if fake_items:
                candidates = []
                for item in final_multiday_sorted:
                    if item.todo not in previous_day and not item.fake_item:
                        candidates.append(item)

                for candidate in candidates:
                    fitem = fake_items.pop(0)
                    final_multiday_sorted.remove(candidate)
                    index = final_multiday_sorted.index(fitem)
                    final_multiday_sorted.remove(fitem)

                    # now replace the empty to the right guy
                    final_multiday_sorted.insert(index, candidate)
                    if not fake_items:
                        break


            # complex sorting for all day events
            # + filter to-dos by date
            non_allday_todos = [t for t in todos if not t.all_day_event
                                        and t not in multiday]
            all_day_todos = [t for t in todos if t.all_day_event
                                        and t not in multiday]
            all_day_todos.sort(sort_by_name_cmp)
            sorted_todos = all_day_todos + non_allday_todos

            mark_private(request.user, [t for t in sorted_todos])

            # check if we have any valid multi-day to-dos
            has_valid = False
            for item in final_multiday_sorted:
                if not item.fake_item:
                    has_valid = True
                    break
            if not has_valid:
                final_multiday_sorted = []

            # now make sure we only show name and time of multi-day
            # todos that are the first ones in a month line
            for item in final_multiday_sorted:
                if item.todo not in previous_day or pos == 0:
                    item.first_multi_day = True
                else:
                    # also set last to-do of the multi-day sequence
                    if item.todo.due_date == day["date"]:
                        item.last_multi_day = True

            # drop leftovers
            leftovers = final_multiday_sorted[:]
            leftovers.reverse()
            for item in leftovers:
                if not item.fake_item:
                    break
                final_multiday_sorted.remove(item)

            multiday_dict[day["date"]] = final_multiday_sorted

            day["todos"] = [TodoCalendarItem(t) for t in sorted_todos]
            day["multiday"] =  final_multiday_sorted

            if mview == MONTHLY_SUMMARY_VIEW:
                day["total_duration"] = todos_total_duration(
                    [t for t in sorted_todos])

            monthl.append(day)
        monthdays.append(monthl)
    return monthdays



def todos_total_duration(todos, format=TOTAL_DURATION_FORMAT,
                         return_raw_values=False):
    u"""Gets a list of to-dos and returns a text describing
    its total duration

    >>> import datetime
    >>> from pursuits.todos.models import (Todo, TOTAL_DURATION_FORMAT,
    ... todos_total_duration)
    >>> from pursuits.general.base_tests import doctest_setup
    >>> sandbox = doctest_setup()
    >>> Todo.objects.all().delete()
    >>> t = Todo(sandbox=sandbox, name="testing",
    ... date=datetime.date.today(),
    ... task_type='Misc', duration=datetime.time(1,2))
    >>> t.save()
    >>> duration = TOTAL_DURATION_FORMAT % (1, 2)
    >>> assert todos_total_duration([t]) == duration
    """
    total_hours = 0
    total_minutes = 0

    # validation errors might return None
    todos = todos or []

    for todo in todos:
        if todo.duration:
            total_hours += todo.duration.hour
            total_minutes += todo.duration.minute

    if total_minutes >= 60:
        total_hours += total_minutes / 60
        total_minutes = total_minutes % 60

    if return_raw_values:
        return total_hours, total_minutes
    return format % (total_hours, total_minutes)


def sort_todos_time_check(x, y):
    """A helper for to-do sorting methods"""
    if x.time and not y.time:
        return -1
    elif y.time and not x.time:
        return 1
    return


def sort_todos_by_priority(todos, ascending=True):
    order = [p for p in Todo.TODO_PRIORITIES]
    if ascending:
        order.reverse()
    order.append('')

    def priority_cmp(x, y):
        pr_cmp = cmp(order.index(x.priority),
                   order.index(y.priority))
        if pr_cmp != 0:
            return pr_cmp
        dcmp = cmp(x.date, y.date) if x.date and y.date else 0
        if dcmp != 0:
            return dcmp

        if not (x.time and y.time):
            return dcmp
        return sort_todos_time_check(x, y) or cmp(x.time, y.time)

    items = list(todos)
    items.sort(priority_cmp)
    return items

def sort_todos_by_datetime(todos, ascending=True):
    todos = list(todos)
    todos.sort(key=lambda todo: (todo.datetime, todo.name), reverse=not ascending)
    return todos

def get_todos_sorting_options():
    """Returns useful sorting options for to-do views - this method is
    also being used by test cases
    """
    options = SortedDict()
    for op in ('date', 'name', 'owner', 'priority', 'project', 'time'):
        # ascending and descending options for each sorting type
        options[u"%s Ascending" % op.title()] = op
        options[u"%s Descending" % op.title()] = u"-%s" % op
    return options


def update_project_milestone_todos(project):
    """For a given project that is connected to a milestone, make sure
    all of its to-dos are also part of the same milestone
    """
    if not project.milestone:
        return

    for todo in project.todos.all():
        todo.milestone = project.milestone
        todo.save()


def todo_timeline_update(todo, creator, action="Updated"):
    """Creates a timeline item for a given to-do action"""
    if todo.parent:
        item_name = u"[%s] %s" % (todo.parent, todo.name)
    else:
        item_name = todo.name
    create_timeline_item(user=creator,
                group_type="To-Do",
                base_url=u"/todos/view/%d/" % todo.id,
                item_name=item_name, action=action)



def send_todo_delegation_notification(todo, newowner, delegator):
    if not newowner or not newowner.get_profile().send_delegation_email:
        return

    delegator_full_name = delegator.get_profile().get_fullname()
    details_str = todo.parent_and_details_str()
    body = DELEGATED_TODO_ASSIGNED_MSG % {
        'USER': newowner.first_name,
        'SENDER': delegator_full_name,
        'TODO': todo.name,
        'DETAILS': u'\n%s' % details_str if details_str else '',
        'REFERER': u"%s/todos/view/%d/" % (
            get_root_website_url(), todo.id),
        'FOOTER': STANDARD_EMAIL_FOOTER}

    email_notify(todo.id, "To-Do Delegation",
        u"[Pursuits] %s has delegated a Todo to you"
        % delegator.first_name, body, newowner.email)


def send_todo_update_notification(todo, changes, sender, status=None):
    sender_full_name = sender.get_profile().get_fullname()
    notified_users = set([uab.user for uab in todo.cc_users_added_by.all()])
    # Notify owner if they're not making the change.
    if sender != todo.owner and todo.owner:
        notified_users.add(todo.owner)
    details_str = todo.parent_and_details_str()
    for user in notified_users:
        body = CHANGED_TODO_NOTIFY % {
            'USER': user.first_name,
            'SENDER': sender_full_name,
            'TODO': todo.name,
            'STATUS': u'%s' %status if status else 'Updated',
            'UPDATE_TODO_NOTIFY': u'%s' %'' if status else UPDATE_TODO_NOTIFY %{'CHANGES':changes},
            'DETAILS': u'\n%s' % details_str if details_str else '',
            'REFERER': u"%s/todos/view/%d/" % (
                get_root_website_url(), todo.id),
            'FOOTER': STANDARD_EMAIL_FOOTER}

        email_notify(todo.id, "To-Do has been updated",
            u"[Pursuits] %s has updated To-Do %s"
            % (sender.first_name, todo.name), body, user.email)


#
# Helpers for Recurrent events
#


class TodoRecurrenceInfo(object):
    def __init__(self, todo):
        self.instance = todo
        # init instance attributes
        # range attributes
        self.r__range_start = self.r__range_type =\
            self.r__range_arg = self.r__recurrence_type =\
            self.r__daily_type = self.r__daily_num =\
            self.r__weekly_repeat_number =\
            self.r__monthly_type = self.r__monthly_g1_num =\
            self.r__monthly_g2_seq = self.r__monthly_g2_weekday =\
            self.r__monthly_g2_num =\
            self.r__yearly_type = self.r__yearly_g1_every =\
            self.r__yearly_g1_day = self.r__yearly_g2_seq =\
            self.r__yearly_g2_weekday = self.r__yearly_g2_month = None
        self.r__weekly_days = SortedDict()
        self._load_recurrence()

    def _fetch_date_from_string(self, date_str):
        args = [int(a) for a in date_str.split("-")]
        return datetime.date(*args)

    def _get_recurr_settings_results(self, regex, settings=None):
        settings = settings or self.instance.repeat_settings
        results = re.search(regex, settings)
        if not results or not results.group(1):
            raise TodoRecurrenceError(
                u"Invalid settings for recurrence, got %s" % settings)
        return results

    def _load_recurrence_range(self):
        rrange = self.instance.repeat_range

        results = self._get_recurr_settings_results(
                r'start:\[(.*)\] end_type:\[(.*)\] end_arg:\[(.*)\]',
                rrange)
        self.r__range_start = self._fetch_date_from_string(
                                    results.group(1))
        end_type = results.group(2)
        end_arg = results.group(3)

        self.r__range_type = end_type
        if end_type == "by_number":
            self.r__range_arg = end_arg

        elif end_type == "by_date":
            self.r__range_arg = self._fetch_date_from_string(end_arg)

        else:
            pass

    def _load_recurrence(self):
        """Loads recurrence data from database and set it as part of the
        form object
        """
        data_dict = {}
        todo = self.instance
        rsettings = todo.repeat_settings
        rrange = todo.repeat_range

        recurr_type = todo.repeat_todo
        if not recurr_type:
            # this to-do has no recurrence
            return

        if recurr_type == Todo.REPEAT_DAILY:
            self.r__recurrence_type = "daily"

            results = self._get_recurr_settings_results(
                                            r'daily\|(days|day):\[(.*)\]')
            self.r__daily_type = results.group(1)
            self.r__daily_num = results.group(2)

        elif recurr_type == Todo.REPEAT_WEEKLY:
            self.r__recurrence_type = "weekly"

            results = self._get_recurr_settings_results(
                            r'weekly\|repeat:\[(\d+)\] days:\[(.*)\]')
            self.r__weekly_repeat_number = results.group(1)
            for weekday in results.group(2).split(","):
                self.r__weekly_days[weekday] = True

        elif recurr_type == Todo.REPEAT_MONTHLY:
            self.r__recurrence_type = "monthly"

            results = self._get_recurr_settings_results(
                                        r'monthly\|(\w{2}) (.*)')
            results_type = results.group(1)
            monthly_settings = results.group(2)

            self.r__monthly_type = results_type
            if results_type == "g1":
                results = re.search(
                    r"day:\[(\d+)\] every:\[(\d+)\]", monthly_settings)
                self.r__monthly_g1_num = results.group(1)
                self.r__monthly_g1_seq = results.group(2)

            else:
                results = re.search(
                    r"day_seq:\[(.*)\] weekday:\[(.*)\] every:\[(\d+)\]",
                    monthly_settings)
                self.r__monthly_g2_seq = results.group(1)
                self.r__monthly_g2_weekday = results.group(2)
                self.r__monthly_g2_num = results.group(3)

        else:
            self.r__recurrence_type = "yearly"

            results = self._get_recurr_settings_results(
                                        r'yearly\|(\w{2}) (.*)')
            results_type = results.group(1)
            yearly_settings = results.group(2)

            self.r__yearly_type = results_type
            if results_type == "g1":
                results = re.search(
                    r"every:\[(.*)\] day:\[(\d+)\]", yearly_settings)
                self.r__yearly_g1_every = results.group(1)
                self.r__yearly_g1_day = results.group(2)

            else:
                results = re.search(
                    r"seq:\[(.*)\] weekday:\[(.*)\] month:\[(.*)\]",
                    yearly_settings)
                self.r__yearly_g2_seq = results.group(1)
                self.r__yearly_g2_weekday = results.group(2)
                self.r__yearly_g2_month = results.group(3)

        #
        # Setting recurrence range
        #

        self._load_recurrence_range()


def _fetch_recurr_max_steps(rinfo):
    range = int(rinfo.r__range_arg)
    max_steps = range if range <= RECUR_MAX_TODOS else RECUR_MAX_TODOS
    recurrence_finished = range <= RECUR_MAX_TODOS
    return max_steps, recurrence_finished


def _fetch_end_date_for_recurrence(rinfo, start_date, limit_days):
    max_end_date = start_date + datetime.timedelta(limit_days)
    if rinfo.r__range_type == "by_date":
        end_date = (rinfo.r__range_arg
                        if rinfo.r__range_arg <= max_end_date
                            else max_end_date)
        recurrence_finished = rinfo.r__range_arg <= max_end_date
    else:
        # never ends
        end_date = start_date + datetime.timedelta(limit_days)
        recurrence_finished = False
    return end_date, recurrence_finished


def create_todo_for_recurrence(parent_todo, new_date, due_date_interval):
    new_todo = Todo()
    for fieldname in RECURRENCE_TODO_FIELDS:
        setattr(new_todo, fieldname, getattr(parent_todo, fieldname))

    new_todo.date = new_date
    new_todo.name = u"%s (R)" % (new_todo.name)
    new_todo.repeat_parent = parent_todo
    new_todo.creator = parent_todo.creator

    if due_date_interval is not None:
        new_todo.due_date = new_date + due_date_interval

    new_todo.save()


def _set_parent_todo_repeated_until_data(todo, rinfo, steps=None,
                        end_date=None, overwrite=True, cleanup=False,
                        save_todo=False):
    if cleanup:
        repeated_until = ''
    else:
        if rinfo.r__range_type == "by_number":
            r_until = todo.repeated_until_obj
            if not overwrite and r_until and r_until.repeat_times > 0:
                steps += r_until.repeat_times
            repeated_until = TODO_REPEATED_UNTIL_FORMAT % (steps, '')
        else:
            repeated_until = TODO_REPEATED_UNTIL_FORMAT % (
                                        0, end_date.strftime("%Y-%m-%d"))

    if save_todo:
        todo.repeated_until = repeated_until
        todo.save()
    else:
        cur = connection.cursor()
        sql = u"update todos_todo set repeated_until=%s where id = %s"
        # use cursor because we don't want to trigger post_save signal again
        cur.execute(sql, [repeated_until, todo.id])


def create_daily_todos(todo, rinfo, start_date, due_date_interval,
                       limit_days, max_end_date=None, save_todo=False):
    steps = 0
    recurrence_finished = False
    end_date = previous_date = None
    if rinfo.r__daily_type == "day":
        every_steps = int(rinfo.r__daily_num)

        if rinfo.r__range_type == "by_number":
            max_steps, recurrence_finished = _fetch_recurr_max_steps(rinfo)
            while steps < max_steps:
                start_date = start_date + datetime.timedelta(
                                                    every_steps)
                if max_end_date and start_date > max_end_date:
                    break
                create_todo_for_recurrence(todo, start_date,
                                           due_date_interval)
                previous_date = start_date
                steps += 1
        else:
            end_date, recurrence_finished = _fetch_end_date_for_recurrence(
                                            rinfo, start_date, limit_days)
            while start_date <= end_date:
                start_date = start_date + datetime.timedelta(
                                                    every_steps)
                if max_end_date and start_date > max_end_date:
                    break
                create_todo_for_recurrence(todo, start_date,
                                           due_date_interval)
                previous_date = start_date

    else:
        # every weekday
        def process_todos(start_date):
            weekday = start_date.strftime("%w")
            if weekday == '5':
                # saturday not allowed, jump to monday
                interv = 3
            elif weekday == '6':
                # saturday not allowed, jump to monday
                interv = 2
            else:
                interv = 1
            start_date = start_date + datetime.timedelta(interv)
            create_todo_for_recurrence(todo, start_date,
                                       due_date_interval)
            return start_date

        if rinfo.r__range_type == "by_number":
            max_steps, recurrence_finished = _fetch_recurr_max_steps(rinfo)
            while steps < max_steps:
                if max_end_date and start_date > max_end_date:
                    break
                start_date = process_todos(start_date)
                previous_date = start_date
                steps += 1
        else:
            end_date, recurrence_finished = _fetch_end_date_for_recurrence(
                                        rinfo, start_date, limit_days)
            while start_date <= end_date:
                if max_end_date and start_date > max_end_date:
                    break
                start_date = process_todos(start_date)
                previous_date = start_date

    if previous_date:
        _set_parent_todo_repeated_until_data(todo, rinfo, steps,
                            previous_date, cleanup=recurrence_finished,
                            save_todo=save_todo)


def _weekly_process_todos(start_date, steps, todo,
                          week_days, due_date_interval, wdays,
                          start_interval):
    WDAYS_DEF = {'0': "sun",
                 '1': 'mon',
                 '2': 'tue',
                 '3': 'wed',
                 '4': 'thu',
                 '5': 'fri',
                 '6': 'sat'}

    start_date = start_date + datetime.timedelta(1)
    weekday = start_date.strftime("%w")
    if WDAYS_DEF[weekday] in wdays.keys():
        create_todo_for_recurrence(todo, start_date,
                                   due_date_interval)
        week_days.pop(0)
        steps += 1

    if not week_days:
        week_days = wdays.keys()[:]
        start_date = start_date + datetime.timedelta(start_interval)
    return start_date, steps, week_days


def create_weekly_todos(todo, rinfo, start_date, due_date_interval,
                        limit_days, max_end_date=None, save_todo=False):
    wdays = rinfo.r__weekly_days
    if not wdays:
        return

    # every weekday
    week_cycle = len(wdays.keys())
    week_days = wdays.keys()[:]

    steps = 0
    recurrence_finished = False
    start_interval = (int(rinfo.r__weekly_repeat_number) -1) * 7
    start_date = start_date + datetime.timedelta(start_interval)
    end_date = previous_date = None

    if rinfo.r__range_type == "by_number":
        max_steps, recurrence_finished  = _fetch_recurr_max_steps(rinfo)
        while steps < max_steps:
            if max_end_date and start_date > max_end_date:
                break
            start_date, steps, week_days = _weekly_process_todos(
                                        start_date, steps, todo,
                                        week_days, due_date_interval,
                                        wdays, start_interval)
            previous_date = start_date

    else:
        end_date, recurrence_finished  = _fetch_end_date_for_recurrence(
                                    rinfo, start_date, limit_days)
        while start_date <= end_date:
            if max_end_date and start_date > max_end_date:
                break
            start_date, steps, week_days = _weekly_process_todos(
                                        start_date, steps, todo,
                                        week_days, due_date_interval,
                                        wdays, start_interval)
            previous_date = start_date

    if previous_date:
        _set_parent_todo_repeated_until_data(todo, rinfo, steps,
                            previous_date, cleanup=recurrence_finished,
                            save_todo=save_todo)


def fetch_weekday_by_name(date, max_seq, selected_day):
    calendar_obj = calendar.Calendar(FIRST_WEEKDAY)
    m_weekdays = calendar_obj.monthdays2calendar(date.year,
                                                 date.month)
    seq = 0
    for m_weekdays_week in m_weekdays:
        for d, w in m_weekdays_week:
            if d == 0:
                continue
            if w != WEEKDAY_NAME_MAPPER[selected_day]:
                continue
            seq += 1
            if seq == max_seq:
                return d
    raise TodoRecurrenceError(
        "oops, we should have returned a valid week day before "
        "reaching this point")


def fetch_week_day(date, max_seq, weekend=False):
    calendar_obj = calendar.Calendar(FIRST_WEEKDAY)
    m_weekdays = calendar_obj.monthdays2calendar(date.year,
                                                 date.month)
    seq = 0
    for m_weekdays_week in m_weekdays:
        for d, w in m_weekdays_week:
            if d == 0:
                continue
            if not weekend:
                if w >= 5:
                    continue
            else:
                if w < 5:
                    continue
            seq += 1
            if seq == max_seq:
                return d
    raise TodoRecurrenceError(
        "oops, we should have returned a valid week day before "
        "reaching this point")


def fetch_weekday_last_day(date):
    calendar_obj = calendar.Calendar(FIRST_WEEKDAY)
    m_weekdays = calendar_obj.monthdays2calendar(date.year,
                                                 date.month)
    m_weekdays.reverse()
    for m_weekdays_week in m_weekdays:
        wline = m_weekdays_week[:]
        wline.reverse()
        for d, w in wline:
            if d != 0 and w < 5:
                return d
    raise TodoRecurrenceError(
        "oops, we should have returned a valid week day before "
        "reaching this point")


def fetch_last_weekday_by_name(date, selected_day):
    calendar_obj = calendar.Calendar(FIRST_WEEKDAY)
    m_weekdays = calendar_obj.monthdays2calendar(date.year,
                                                 date.month)
    m_weekdays.reverse()
    for m_weekdays_week in m_weekdays:
        wline = m_weekdays_week[:]
        wline.reverse()
        for d, w in wline:
            if d != 0 and w == WEEKDAY_NAME_MAPPER[selected_day]:
                return d
    raise TodoRecurrenceError(
        "oops, we should have returned a valid week day before "
        "reaching this point")


def fetch_weekend_last_day(date):
    calendar_obj = calendar.Calendar(FIRST_WEEKDAY)
    m_weekdays = calendar_obj.monthdays2calendar(date.year,
                                                 date.month)
    last_week = m_weekdays[-1]
    last_week.reverse()
    for mday, wday in last_week:
        if mday != 0 and wday >= 5:
            return mday
    raise TodoRecurrenceError(
        "oops, we should have returned a valid weekend day before "
        "reaching this point")


def new_monthly_date(date, month_increment, month_day):
    for i in range(month_increment):
        if date.month + 1 > 12:
            date = datetime.date(date.year + 1, 1, month_day)
        else:
            date = datetime.date(date.year, date.month + 1, month_day)
    return date


def fetch_day_by_complex_parameters(date, weekday, day_seq):
    if weekday == 'day':
        if day_seq == 'first':
            day = 1
        elif day_seq == 'second':
            day = 2
        elif day_seq == 'third':
            day = 3
        elif day_seq == 'fourth':
            day = 4
        else:
            # last day, not so obvious
            day = calendar.monthrange(date.year, date.month)[1]

    elif weekday == "weekday":
        if day_seq == 'first':
            day = fetch_week_day(date, 1)

        elif day_seq == 'second':
            day = fetch_week_day(date, 2)

        elif day_seq == 'third':
            day = fetch_week_day(date, 3)

        elif day_seq == 'fourth':
            day = fetch_week_day(date, 4)
        else:
            # last day, not so obvious
            day = fetch_weekday_last_day(date)

    elif weekday == "weekend day":
        if day_seq == 'first':
            day = fetch_week_day(date, 1, weekend=True)

        elif day_seq == 'second':
            day = fetch_week_day(date, 2, weekend=True)

        elif day_seq == 'third':
            day = fetch_week_day(date, 3, weekend=True)

        elif day_seq == 'fourth':
            day = fetch_week_day(date, 4, weekend=True)
        else:
            # last day, not so obvious
            day = fetch_weekend_last_day(date)

    else:
        # finally fucking Outlook made things a bit easier
        # just check for specific day names of the week:
        # monday, tuesday, etc
        if day_seq == 'first':
            day = fetch_weekday_by_name(date, 1, weekday)

        elif day_seq == 'second':
            day = fetch_weekday_by_name(date, 2, weekday)

        elif day_seq == 'third':
            day = fetch_weekday_by_name(date, 3, weekday)

        elif day_seq == 'fourth':
            day = fetch_weekday_by_name(date, 4, weekday)

        else:
            # last day, not so obvious again...
            day = fetch_last_weekday_by_name(date, weekday)
    return day


def new_seq_monthly_date(date, day_seq, weekday, month_increment):
    for i in range(month_increment):
        if date.month + 1 > 12:
            date = datetime.date(date.year + 1, 1, 1)
        else:
            date = datetime.date(date.year, date.month + 1, 1)

        day = fetch_day_by_complex_parameters(date, weekday, day_seq)
        date = date.replace(day=day)
    return date


def create_monthly_todos(todo, rinfo, start_date, due_date_interval,
                         limit_days, max_end_date=None, save_todo=False):
    steps = 0
    recurrence_finished = False
    end_date = previous_date = None
    if rinfo.r__monthly_type == "g1":
        day_num = int(rinfo.r__monthly_g1_num)
        month_seq = int(rinfo.r__monthly_g1_seq)

        if rinfo.r__range_type == "by_number":
            max_steps, recurrence_finished = _fetch_recurr_max_steps(rinfo)
            while steps < max_steps:
                start_date = new_monthly_date(start_date,
                                              month_seq, day_num)
                if max_end_date and start_date > max_end_date:
                    break
                create_todo_for_recurrence(todo, start_date,
                                           due_date_interval)
                previous_date = start_date
                steps += 1
        else:
            end_date, recurrence_finished = _fetch_end_date_for_recurrence(
                                            rinfo, start_date, limit_days)
            start_date = new_monthly_date(start_date,
                                          month_seq, day_num)
            while start_date <= end_date:
                if max_end_date and start_date > max_end_date:
                    break
                create_todo_for_recurrence(todo, start_date,
                                           due_date_interval)
                previous_date = start_date
                start_date = new_monthly_date(start_date,
                                              month_seq, day_num)
    else:
        # group 2
        day_seq = rinfo.r__monthly_g2_seq
        weekday = rinfo.r__monthly_g2_weekday
        month_increment = int(rinfo.r__monthly_g2_num)

        if rinfo.r__range_type == "by_number":
            max_steps, recurrence_finished = _fetch_recurr_max_steps(rinfo)
            while steps < max_steps:
                start_date = new_seq_monthly_date(start_date, day_seq,
                                        weekday, month_increment)
                if max_end_date and start_date > max_end_date:
                    break
                create_todo_for_recurrence(todo, start_date,
                                           due_date_interval)
                previous_date = start_date
                steps += 1
        else:
            end_date, recurrence_finished  = _fetch_end_date_for_recurrence(
                                    rinfo, start_date, limit_days)
            start_date = new_seq_monthly_date(start_date, day_seq,
                                    weekday, month_increment)
            while start_date <= end_date:
                if max_end_date and start_date > max_end_date:
                    break
                create_todo_for_recurrence(todo, start_date,
                                           due_date_interval)
                previous_date = start_date
                start_date = new_seq_monthly_date(start_date, day_seq,
                                        weekday, month_increment)

    if previous_date:
        _set_parent_todo_repeated_until_data(todo, rinfo, steps,
                            previous_date, cleanup=recurrence_finished,
                            save_todo=save_todo)



def new_yearly_g1_date(start_date, month_number, month_day):
    # TODO need to add form validation for month day,
    # some months like Feb doesn't accept 31 days
    return datetime.date(start_date.year + 1,
                            month_number, month_day)


def new_yearly_g2_date(date, day_seq, weekday, month_name):
    # increase year
    date = date.replace(year=date.year + 1)

    MONTH_NAMES = {}
    for i in range(1, 13):
        MONTH_NAMES[datetime.date(2009,i,1).strftime("%B")] = i

    # use the month desired by user
    month_number = MONTH_NAMES[month_name]
    date = date.replace(month=month_number)

    day = fetch_day_by_complex_parameters(date, weekday, day_seq)
    return date.replace(day=day)


def create_yearly_todos(todo, rinfo, start_date, due_date_interval,
                        limit_days, max_end_date=None, save_todo=False):
    MONTH_NAMES = {}
    for i in range(1, 13):
        MONTH_NAMES[datetime.date(2009,i,1).strftime("%B")] = i

    steps = 0
    recurrence_finished = False
    end_date = previous_date = None
    if rinfo.r__yearly_type == "g1":
        every_month = rinfo.r__yearly_g1_every
        month_number = MONTH_NAMES[every_month]

        month_day = int(rinfo.r__yearly_g1_day)

        if rinfo.r__range_type == "by_number":
            max_steps, recurrence_finished = _fetch_recurr_max_steps(rinfo)
            while steps < max_steps:
                start_date = new_yearly_g1_date(start_date,
                                             month_number, month_day)
                if max_end_date and start_date > max_end_date:
                    break
                create_todo_for_recurrence(todo, start_date,
                                           due_date_interval)
                previous_date = start_date
                steps += 1
        else:
            end_date, recurrence_finished = _fetch_end_date_for_recurrence(
                                            rinfo, start_date, limit_days)
            start_date = new_yearly_g1_date(start_date,
                                         month_number, month_day)
            while start_date <= end_date:
                if max_end_date and start_date > max_end_date:
                    break
                create_todo_for_recurrence(todo, start_date,
                                           due_date_interval)
                previous_date = start_date
                start_date = new_yearly_g1_date(start_date,
                                             month_number, month_day)
    else:
        # group 2
        day_seq = rinfo.r__yearly_g2_seq
        weekday = rinfo.r__yearly_g2_weekday
        month_name = rinfo.r__yearly_g2_month

        if rinfo.r__range_type == "by_number":
            max_steps, recurrence_finished = _fetch_recurr_max_steps(rinfo)
            while steps < max_steps:
                start_date = new_yearly_g2_date(start_date, day_seq,
                                                weekday, month_name)
                if max_end_date and start_date > max_end_date:
                    break
                create_todo_for_recurrence(todo, start_date,
                                           due_date_interval)
                previous_date = start_date
                steps += 1
        else:
            end_date, recurrence_finished = _fetch_end_date_for_recurrence(
                                        rinfo, start_date, limit_days)
            start_date = new_yearly_g2_date(start_date, day_seq,
                                            weekday, month_name)
            while start_date <= end_date:
                if max_end_date and start_date > max_end_date:
                    break
                create_todo_for_recurrence(todo, start_date,
                                           due_date_interval)
                previous_date = start_date
                start_date = new_yearly_g2_date(start_date, day_seq,
                                                weekday, month_name)

    if previous_date:
        _set_parent_todo_repeated_until_data(todo, rinfo, steps,
                            previous_date, cleanup=recurrence_finished,
                            save_todo=save_todo)


#
# Models
#


class Todo(models.Model):
    """Todos are an integral part of pursuits. The represent a discrete task
    that a user may want to perform that can be completed in one sitting. They
    can be "attached" to other entities, notably group projects and projects.
    Project todos are measured in scorecards.  Todos with a time are meetings.
    """

    DISPLAY_TIME_AS = { 0: "Free",
                        1: "Tentative",
                        2: "Busy",
                        3: "Out of Office" }
    # 2 means Busy according to DISPLAY_TIME_AS symbol
    DEFAULT_DISPLAY_TIME_AS = 2

    # priorites on descending order
    TODO_PRIORITIES = ("C",
                       "B",
                       "A",
                       "AA",
                       "Word")

    SHORT_TODO_PRIORITIES = SortedDict((
                       ("C", "C"),
                       ("B", "B"),
                       ("A", "A"),
                       ("AA", "!"),
                       ("Word", "W")))

    REPEAT_TYPES = (REPEAT_DAILY,
                    REPEAT_WEEKLY,
                    REPEAT_MONTHLY,
                    REPEAT_YEARLY) = range(1, 5)

    REPEAT_TYPES_DESC = {REPEAT_DAILY: "Daily",
                         REPEAT_WEEKLY: "Weekly",
                         REPEAT_MONTHLY: "Monthly",
                         REPEAT_YEARLY: "Yearly"}

    objects = PursuitsManager()


    repeat_todo = models.IntegerField(blank=True, null=True,
                            choices=REPEAT_TYPES_DESC.items())
    # when the recurrency stars/ends or if it never ends
    repeat_range = models.CharField(max_length=256,
                                    blank=True, null=True)
    # settings for daily/weekly/monthly/yearly recurrencies
    repeat_settings = models.CharField(max_length=256,
                                       blank=True, null=True)
    # stores a reference of current state of repeat information
    # so we can compare every time we update a to-do and see if the recurrence
    # needs to be created again
    repeat_data = models.TextField(null=True, blank=True)
    # keep trac of how many to-dos we created so far for this recurrence
    # a cron job is in charge of creating more to-dos for long term
    # recurrences as the time goes on
    # Note that if this field is empty it means that
    # there is no more to-dos to be created
    repeated_until = models.CharField(max_length=256,
                                      null=True, blank=True)

    # this is the to-do that originated a recurrence
    repeat_parent = models.ForeignKey("self", null=True, blank=True)

    sandbox = models.ForeignKey("general.Sandbox")
    creator = models.ForeignKey(User, related_name="todo_creator")
    owner = models.ForeignKey(User, blank=True, null=True)
    milestone = models.ForeignKey("group_projects.Milestone", blank=True,
                                  null=True, related_name="todos")

    # defines whether or not this to-do has been marked during
    # a meeting or there is anything special about it
    marked = models.BooleanField(default=False)

    # deleted to-dos are cloned so managers can supervise
    deleted_on = LocalizedDateTimeField(null=True, blank=True)
    cloned_from_deleted = models.BooleanField(default=False)
    deleted_by = models.ForeignKey(User,
                        null=True, blank=True,
                        related_name="todos_deleted_by")

    name = models.CharField(max_length=256)
    date = models.DateField(blank=True, null=True)
    due_date = models.DateField(blank=True, null=True)
    due_date_time = models.TimeField(blank=True, null=True)
    all_day_event = models.BooleanField(default=False)
    deadline_notification_sent = models.BooleanField(default=False)
    
    created_at = LocalizedDateTimeField(auto_now_add=True)
    last_updated = LocalizedDateTimeField(auto_now=True)
    time = models.TimeField(null=True, blank=True)

    task_type = models.CharField(
        max_length=255,
        choices=make_choice(TODO_TASK_TYPES)
    )
    details = models.TextField(blank=True)
    # TODO: Django has a Duration Field, but it hasn't
    # been accepted. We should take advantage of it, either
    # after the patch is accepted, or we could copy the
    # code for now and merge it later. (Django ticket #2443)
    duration = models.TimeField(null= True, blank=True)
    actual_duration = models.TimeField(null= True, blank=True)

    priority = models.CharField(
        max_length=4,
        choices = make_choice(TODO_PRIORITIES), blank=True)
    tough_one = models.BooleanField(default=False)
    private = models.BooleanField(default=False)
    task_analysis = models.CharField(
            blank=True,
            max_length=16,
            choices = make_choice([
                "Repetitive",
                "Problem Solving",
                "Planning"]))
    status = models.CharField(
        max_length=15,
        # TODO this should use symbols instead of strings
        choices = make_choice([
            "Active",
            "Completed",
            "Limbo",
            "Inactive"
        ]),
        default="Active")
    monitoring_users = models.ManyToManyField(User,
            related_name="monitored_todos", null=True, blank=True)
    anonymous_owner_key = models.CharField(
            max_length=65, blank=True)
    brought_forward = models.PositiveIntegerField(default=0)
    completed_at = LocalizedDateTimeField(null=True, blank=True)

    reminder_dismissed = models.BooleanField(default=False)
    reminder_notified = models.BooleanField(default=False)
    remind_before = models.CharField("Notification before",
                max_length=80, null=True, blank=True,
                choices=make_choice(REMINDER_TYPES))
    reminder_email = models.BooleanField("Notification e-mail",
                                         default=False)
    reminder_email_sent = models.BooleanField(default=False)
    reminder_popup = models.BooleanField("Notification pop-up",
                                         default=False)
    calendar_event = models.BooleanField(default=False)
    display_time_as = models.IntegerField(
            default=DEFAULT_DISPLAY_TIME_AS, blank=True,
            # this should be mapped to the int value in Outlook
            choices=DISPLAY_TIME_AS.items())
    comments = models.ManyToManyField(Note, blank=True, null=True)
    documents = models.ManyToManyField("cms.Document" , blank=True,
                                       null=True)
    cc_users_added_by = generic.GenericRelation(UserAddedBy)

    class Meta:
        permissions = (
                ("edit_any_todo",
                 "Can view or edit any user's todos"),
        )

    def __unicode__(self):
        '''return a string representation of the todo -- the name and date'''
        return self.name

    def get_absolute_url(self):
        return '/todos/view/%s/' % self.id
    
    def user_can_access_todo(self, user):
        # The only way a user *can't* access a to-do is if it has an owner
        # that is not the user, it is marked private, and the user is not an
        # admin.
        return (not self.owner or
                not self.private or
                self.owner == user or
                is_admin(user))

    def user_can_edit_todo(self, user):
        # If you have access, you can edit.
        return self.user_can_access_todo(user)

    @property
    def duration_as_str(self):
        return self.duration.strftime("%H:%M")

    @property
    def repeated_until_obj(self):
        if not self.repeat_todo or not self.repeated_until:
            return

        class TodoRepeatUntil(object):
            def __init__(self, rtimes, rdate):
                self.repeat_times = int(rtimes)
                self.repeat_date = rdate or None

        result = re.search(r'rtimes:\[(\d+)\] rdate:\[(.*)\]',
                                        self.repeated_until or '')
        rtimes = result.group(1)
        rdate = result.group(2)
        if rdate:
            # dates are stored in the format: yyyy-mm-dd
            rdate = datetime.date(*[int(arg) for arg in rdate.split('-')])
        return TodoRepeatUntil(rtimes, rdate)

    @property
    def all_edps(self):
        return self.edp_set.all().order_by('first_name', 'last_name')

    @property
    def has_recurrence(self):
        return self.repeat_todo is not None

    @property
    def repeat_data_as_dict(self):
        # loads the content of repeat_data as a python dict
        if not self.repeat_data:
            return
        decoded = base64.decodestring(self.repeat_data)
        return pickle.loads(decoded)

    @property
    def wrap_details(self):
        return insert_url_elements_into_text(wrap(self.details, 120))

    @property
    def todo_obj(self):
        "Lets a Todo impersonate a TodoView in some templates."
        return self

    @property
    def todoview(self):
        "Return the TodoView for this todo."
        from pursuits.general.dbviews import TodoView
        return TodoView.objects.get(id=self.id)
    
    @property
    def owner_choices(self):
        "Cached owner user choices."
        key = 'todo_owner_choices'
        choices = cache.get(key)
        if choices:
            return choices
        choices = [(u.id, u.username) for u in
                   self.sandbox.all_users.order_by('username')]
        cache.set(key, choices, TODO_OWNER_CHOICES_TIMEOUT)
        return choices

    @property
    def datetime(self):
        """
        Return starting date and time combined into a datetime object.
        If there is a date and no time, use 0:00 (midnight) as the time.
        If there is no date, return None.
        """
        if self.date:
            return datetime.datetime.combine(
                self.date, self.time or datetime.time(0, 0))
        else:
            return None
       
    def dependency_graph_number(self):
        """
        Returns the graph number of this todo's dependencies.
        Returns None if this todo has no dependencies.
        """
        from pursuits.dependency.models import Dependency
        return Dependency.objects.graph_number_for_todo(self)

    def has_dependencies(self):
        return self.dependency_graph_number() is not None
    
    def get_parent(self, ignore_gp=False):
        """returns the parent of this todo -- what its attached to

        ** First testing parent for Project:

        >>> import datetime
        >>> from django.contrib.auth.models import User
        >>> from pursuits.todos.models import Todo
        >>> from pursuits.coaching.models import EDP
        >>> from pursuits.group_projects.models import (GroupProject,
        ... Milestone)
        >>> from pursuits.projects.models import Project, CRMProject
        >>> from pursuits.general.base_tests import doctest_setup
        >>> sandbox = doctest_setup()
        >>> Project.objects.all().delete()
        >>> Todo.objects.all().delete()
        >>> t = Todo(name="testing", date=datetime.date.today(),
        ... task_type='Misc', sandbox=sandbox)
        >>> t.save()
        >>> assert not t.parent
        >>> p = Project(name="testing", sandbox=sandbox)
        >>> p.save()
        >>> p.todos.add(t)
        >>> isinstance(t.parent, Project)
        True

        ** Testing CRMProject as parent:

        >>> Project.objects.all().delete()
        >>> CRMProject.objects.all().delete()
        >>> Todo.objects.all().delete()
        >>> t = Todo(name="testing", date=datetime.date.today(),
        ... task_type='Misc', sandbox=sandbox)
        >>> t.save()
        >>> assert not t.parent
        >>> p = CRMProject(sandbox=sandbox)
        >>> p.save()
        >>> p.todos.add(t)
        >>> isinstance(t.parent, CRMProject)
        True


        ** Testing EDP as parent:

        >>> CRMProject.objects.all().delete()
        >>> EDP.objects.all().delete()
        >>> Todo.objects.all().delete()
        >>> t2 = Todo.objects.create(name="testing", date=datetime.date.today(),
        ... task_type='Misc', sandbox=sandbox)
        >>> assert not t2.parent
        >>> u = User.objects.create_user(username='edp_tester',
        ... email='tester@pursuits.com')
        >>> edp_obj = EDP.objects.create(first_name="test", last_name="last",
        ... coach=u, sandbox=sandbox)
        >>> edp_obj.todos.add(t2)
        >>> isinstance(t2.parent, EDP)
        True

        ** Testing GroupProject's milestone as parent:

        >>> EDP.objects.all().delete()
        >>> Todo.objects.all().delete()
        >>> Milestone.objects.all().delete()
        >>> GroupProject.objects.all().delete()
        >>> m = Milestone.objects.create(name="test", sandbox=sandbox,
        ... date=datetime.date.today())
        >>> gp = GroupProject.objects.create(name="testx", gp_type="Sales",
        ... status="Current", sandbox=sandbox)
        >>> gp.milestones.add(m)
        >>> t = Todo.objects.create(name="testing", sandbox=sandbox,
        ... date=datetime.date.today(), task_type='Misc', milestone=m)
        >>> isinstance(t.parent, GroupProject)
        True

        >>> t.parent.milestones.count()
        1L

        >>> assert t.parent.milestones.all()[0] == m, "Got invalid milestone"
        """
        # Cache parent on model to save repeating queries multiple times.
        if hasattr(self, '_parent'):
            return self._parent
        self._parent = None
        if not self.id:
            self._parent = None
        elif self.milestone and not ignore_gp:
            if self.milestone.groupproject_set.count() > 0:
                self._parent = self.milestone.groupproject_set.all()[0]
        elif self.groupproject_set.count() > 0:
            self._parent = self.groupproject_set.all()[0]
        elif self.crmproject_set.undeleted().count() > 0:
            self._parent = self.crmproject_set.undeleted()[0]
        elif self.edp_set.undeleted().count() > 0:
            self._parent = self.edp_set.undeleted()[0]
        elif self.fiveminutemeeting.count() > 0:
            self._parent = self.fiveminutemeeting.all()[0]
        elif self.decision_set.count() > 0:
            self._parent = self.decision_set.all()[0]
        return self._parent
    parent = property(get_parent)

    @property
    def full_view_url(self):
        return u"%s/todos/view/%d/" % (get_root_website_url(), self.id)

    def _get_edit_url(self):
        """Return an url to the edit page for this object

        The doctest below might look a bit silly but it's good to
        make sure we are always returning something useful without a crash.

        >>> from pursuits.todos.models import Todo
        >>> from pursuits.general.base_tests import doctest_setup
        >>> sandbox = doctest_setup()
        >>> Todo.objects.all().delete()
        >>> t = Todo(name="testing", date=datetime.date.today(),
        ... task_type='Misc', sandbox=sandbox)
        >>> t.save()
        >>> assert t.edit_url is not None
        >>> assert len(t.edit_url) > 0
        """
        return u"/todos/edit/%d/" % (self.id)
    edit_url = property(_get_edit_url)

    def _is_overdue(self):
        """Return true if this todo is overdue (the date is before today and
        the status is not completed

        >>> from pursuits.todos.models import Todo
        >>> from pursuits.general.base_tests import doctest_setup
        >>> sandbox = doctest_setup()
        >>> Todo.objects.all().delete()
        >>> t = Todo(name="testing", date=datetime.date.today(),
        ... task_type='Misc', sandbox=sandbox)
        >>> t.save()
        >>> assert t.overdue == False
        >>> t.date = datetime.date.today() - datetime.timedelta(2)
        >>> assert t.overdue == True
        """
        if self.status == "Completed":
            return False
        if self.date < datetime.date.today():
            return True
        return False
    overdue = property(_is_overdue)

    @property
    def due_date_overdue(self):
        return self.due_date and self.due_date < datetime.date.today()

    @property
    def due_datetime(self):
        """
        As with datetime() above, but returns the ending date and time combined 
        into a datetime object. If there is a date and no time, use 0:00 (midnight) 
        as the time. If there is no date, return None.
        """
        if self.due_date:
            return datetime.datetime.combine(
                self.due_date, self.due_date_time or datetime.time(0, 0))
        else:
            return None

    @property
    def multiday_event(self):
        return (self.date and self.due_date and
                self.date < self.due_date)

    def _get_reminder_seconds(self):
        if not self.remind_before:
            return
        if self.remind_before in REMINDER_TYPES:
            return REMINDER_TYPES[self.remind_before]
        raise DatabaseInconsistency(
            u"Invalid reminder type for todo %s, got %s"
            % (self, self.remind_before))
    reminder_seconds = property(_get_reminder_seconds)
    
    def activate(self):
        if not self.is_draft:
            raise TodoError(
                u"Can't activate to-do with status %s" % self.status)
        self.status = "Active"

        profile = get_current_user().get_profile()
        allow_null = profile.milestone_allow_nulldate_for_unassigned_todo
        inc_days = profile.milestone_todo_date_inc_on_activation
        if not self.date or self.date < datetime.date.today():
            if self.parent_is_group_project and allow_null and not self.owner:
                self.date = None
            else:
                self.date = datetime.datetime.now() + datetime.timedelta(
                        inc_days)
        self.save()

    @property
    def duration_in_minutes(self):
        return (self.duration.hour * 60) + self.duration.minute

    @property
    def dta_code(self):
        '''get the display time as code '''
        return title_to_code(self.display_time_as)

    @property
    def parent_is_group_project(self):
        from pursuits.group_projects.models import GroupProject
        return isinstance(self.parent, GroupProject)

    @property
    def is_completed(self):
        return self.status == "Completed"

    @property
    def is_draft(self):
        return self.status == "Inactive"

    @property
    def is_active(self):
        return self.status == "Active"

    @property
    def is_limbo(self):
        return self.status == "Limbo"

    @property
    def is_closed(self):
        """checkes wheter this to-do has an status other than
        active/draft - this is useful for implementation plan and
        milestones.
        """
        return self.status in ("Completed", "Limbo", "Deleted")

    @property
    def priority_short_format(self):
        """Returns the priority of the to-do in one character format."""
        if not self.priority:
            return ''
        return Todo.SHORT_TODO_PRIORITIES[self.priority]

    @property
    def creator_fullname(self):
        return self.creator.get_profile.get_fullname()

    def parent_and_details_str(self):
        """
        For DETAILS variable in email templates: include parent info
        if it exists.
        """
        from pursuits.group_projects.models import GroupProject
        from pursuits.projects.models import CRMProject
        from pursuits.group_projects.models import Milestone
        from pursuits.coaching.models import EDP
        from pursuits.group_projects.models import FiveMinuteMeeting
        from pursuits.projects.models import Decision
        details_str = u'Parent : '
        parent = self.get_parent()
        # @question Is there any reason not to use parent's __unicode__ for parent_and_details_str?
        if parent:
            if isinstance(parent, GroupProject):
                details_str += u"Project '%s'\n" % parent.name
            elif isinstance(parent, CRMProject):
                details_str += u"CRM Project '%s'\n" % parent.name
            elif isinstance(parent,Milestone):
                details_str += u"Project '%s'\n" % parent.group_project.name
                details_str += u"Milestone : '%s'\n" % parent.name
            elif isinstance(parent,EDP):
                details_str += u"EDP '%s'\n" % parent.full_name
            elif isinstance(parent,FiveMinuteMeeting):
                details_str += u"Five Minute Meeting '%s'\n" %parent
            elif isinstance(parent,Decision):
                details_str += u"Decision '%s'\n" %parent
        else:
            details_str += u"Standalone To-Do\n"
        details_str = u"%sDetails : %s" % (details_str, self.details)
        return details_str

    def get_parent_type(self):
        """Return the type of the parent (as a string) or None if it is a standalone todo."""
        from pursuits.group_projects.models import GroupProject
        from pursuits.projects.models import CRMProject
        from pursuits.group_projects.models import Milestone
        from pursuits.coaching.models import EDP
        from pursuits.group_projects.models import FiveMinuteMeeting
        from pursuits.projects.models import Decision
        parent = self.get_parent()
        if parent:
            if isinstance(parent, GroupProject):
                return 'groupproject'
            elif isinstance(parent, CRMProject):
                return 'crmproject'
            elif isinstance(parent,Milestone):
                return 'milestone'
            elif isinstance(parent,EDP):
                return 'edp'
            elif isinstance(parent,FiveMinuteMeeting):
                return 'fiveminutemeeting'
            elif isinstance(parent,Decision):
                return 'decision'
            else:
                return None
        else:
            return None

    def save(self, *args, **kwargs):
        # Set default reminder time if necessary.
        if (self.remind_before and
            (self.reminder_email or self.reminder_popup) and
            not self.time):
            try:
                self.time = get_current_user().get_profile().\
                    todo_default_start_time
            except SandboxError:
                pass
        super(Todo, self).save(*args, **kwargs)
    
    @classmethod
    def save_note_callback(cls, sender, instance, note_instance,
                           **kwargs):
        if instance.parent:
            item_name = u"[%s] %s" % (instance.parent, instance.name)
        else:
            item_name = instance.name

        if len(item_name) > 200:
            item_name = item_name[:200] + '...'
        create_timeline_item(user=note_instance.creator,
                    group_type="To-Do",
                    base_url=u"/todos/view/%d/" % instance.id,
                    item_name=item_name,
                    action="New Comment", note=note_instance)
        changes = u"Added comment:\n%s" % note_instance.comment
        send_todo_update_notification(instance, changes,
                                note_instance.creator)

    @classmethod
    def save_todo_creator(cls, sender, instance, **kwargs):
        if not instance.id and not instance.creator_id:
            instance.creator = get_current_user()


    @classmethod
    def document_post_save(cls, sender, instance,
            doc_instance, creator, is_new_model,
            action="", **kwargs):
        create_timeline_item(user=creator,
                    group_type="To-Do",
                    base_url=instance.edit_url,
                    item_name=instance.name,
                    attachment=doc_instance,
                    action=(action or ("Document Uploaded"
                        if is_new_model else "Document Updated")))
        if action:
            changes = u"%s: '%s'" % (action, doc_instance.title)
        else:
            changes = u"Added document '%s'" % doc_instance.title
        send_todo_update_notification(instance, changes, creator)

    @classmethod
    def notify_monitoring_users_on_delete(
            cls, sender, instance, **kwargs):
        notified_users = set(instance.monitoring_users.all())
        # Notify owner if they're not the one deleting.
        try:
            current_user = get_current_user()
        except SandboxError:  # For cron jobs; no user is registered.
            current_user = None
        if (current_user and current_user != instance.owner and
            instance.owner) or not current_user:
            notified_users.add(instance.owner)
        sender = current_user and current_user.get_full_name() or 'Pursuits'
        details_str = instance.parent_and_details_str()
        for muser in notified_users:
            body = DELEGATED_TODO_DELETED_MSG % {
                'USER': muser.first_name,
                'SENDER': sender,
                'TODO': instance.name,
                'DETAILS': u'\n%s' % details_str if details_str else '',
                'FOOTER': STANDARD_EMAIL_FOOTER}

            email_notify(instance.id, "monitored to-do deleted",
                         u"Monitored To-Do deleted by %s" % sender,
                         body, muser.email)

        # deleted must be cloned for auditing
        if not instance.cloned_from_deleted:
            instance.id = None
            instance.status = "Inactive"
            instance.deleted_by = current_user
            instance.cloned_from_deleted = True
            instance.deleted_on = datetime.datetime.now()
            instance.save()


post_save_document_signal.connect(Todo.document_post_save,
                                  sender=Todo)
pre_save.connect(Todo.save_todo_creator, sender=Todo)
post_save_notes_signal.connect(Todo.save_note_callback, sender=Todo)
pre_delete.connect(Todo.notify_monitoring_users_on_delete, sender=Todo)



@transaction.commit_on_success
def update_todo_recurring_events(todo):
    recurr_type = todo.repeat_todo
    if not recurr_type:
        return

    new_repeat_data_dict = {}
    for field in RECURRENCE_TODO_FIELDS + (
                        "repeat_range", "repeat_settings"):
        new_repeat_data_dict[field] = getattr(todo, field)

    original_repeat_data = todo.repeat_data_as_dict

    if todo.repeat_data and new_repeat_data_dict == original_repeat_data:
        # skip it, nothing has changed in the recurring area
        return
    else:
        cur = connection.cursor()
        sql = u"update todos_todo set repeat_data=%s where id = %s"
        # use cursor because we don't want to trigger post_save signal again
        pickled_repeat_data = pickle.dumps(new_repeat_data_dict)
        encoded = base64.encodestring(pickled_repeat_data)
        cur.execute(sql, [encoded, todo.id])

    recurrence_generated = Todo.objects.filter(
            repeat_parent=todo).count() > 0

    if recurrence_generated:
        # TODO we should ask user confirmation before doing this
        #
        # drop to-dos already created, we will create new ones based on
        # new recurrence settings
        Todo.objects.filter(repeat_parent=todo,
                            status__in=["Active", "Limbo", "Inactive"]
                            ).delete()

    todo_id = todo.id
    rinfo = TodoRecurrenceInfo(todo)
    limit_days = RECUR_MAX_DAYS_CREATE_TODOS

    due_date_interval = (todo.due_date - todo.date if todo.due_date
                         else None)
    start_date = rinfo.r__range_start

    if recurr_type == Todo.REPEAT_DAILY:
        create_daily_todos(todo, rinfo, start_date, due_date_interval,
                           limit_days)

    elif recurr_type == Todo.REPEAT_WEEKLY:
        create_weekly_todos(todo, rinfo, start_date, due_date_interval,
                            limit_days)

    elif recurr_type == Todo.REPEAT_MONTHLY:
        create_monthly_todos(todo, rinfo, start_date, due_date_interval,
                             limit_days)

    else: # yearly
        create_yearly_todos(todo, rinfo, start_date, due_date_interval,
                            limit_days)


@transaction.commit_on_success
def check_missing_todo_recurring_events():
    """This method should be called only by cron scripts"""
    todos = Todo.objects.filter(repeat_todo__isnull=False,
                        repeated_until__isnull=False,
                        repeat_parent__isnull=True,
                        status__in=["Active", "Limbo"])

    for todo in todos:
        todo_id = todo.id
        recurr_type = todo.repeat_todo
        rinfo = TodoRecurrenceInfo(todo)
        limit_days = RECUR_MAX_DAYS_CREATE_TODOS

        due_date_interval = (todo.due_date - todo.date if todo.due_date
                             else None)
        start_date = rinfo.r__range_start
        max_end_date = datetime.date.today() + datetime.timedelta(
                        RECUR_MAX_DAYS_CREATE_TODOS
                        )

        runtil = todo.repeated_until_obj
        if runtil and runtil.repeat_date:
            start_date = runtil.repeat_date

        if recurr_type == Todo.REPEAT_DAILY:
            create_daily_todos(todo, rinfo, start_date, due_date_interval,
                               limit_days, max_end_date, save_todo=True)

        elif recurr_type == Todo.REPEAT_WEEKLY:
            create_weekly_todos(todo, rinfo, start_date, due_date_interval,
                                limit_days, max_end_date, save_todo=True)

        elif recurr_type == Todo.REPEAT_MONTHLY:
            create_monthly_todos(todo, rinfo, start_date, due_date_interval,
                                 limit_days, max_end_date, save_todo=True)

        else: # yearly
            create_yearly_todos(todo, rinfo, start_date, due_date_interval,
                                limit_days, max_end_date, save_todo=True)



def todo_post_save(sender, instance, **kwargs):
    """Signal to set the completion date when a todo is first marked as
    complete.

    >>> import datetime
    >>> from pursuits.todos.models import Todo
    >>> from pursuits.general.base_tests import doctest_setup
    >>> sandbox = doctest_setup()
    >>> Todo.objects.all().delete()
    >>> t = Todo(name="testing", date=datetime.date.today(),
    ... task_type='Misc', sandbox=sandbox)
    >>> t.save()
    >>> assert t.completed_at is None
    >>> t.status = 'Completed'
    >>> t.save()
    >>> assert t.completed_at is not None
    """
    if not instance.completed_at and instance.status == "Completed":
        instance.completed_at = datetime.datetime.today()
        instance.save()
    update_todo_recurring_events(instance)

post_save.connect(todo_post_save, sender=Todo)


class ClusterItem(models.Model):
    '''Represents a single item in a weekly cluster. Clutering maintains a
    different value from the set (Prep, Comm, Meet) for each user for each day
    of the week for each of four time quadrants. One clusteritem represents one
    of these values'''

    def __unicode__(self):
        return self.owner.get_full_name()

    objects = PursuitsManager()

    sandbox = models.ForeignKey("general.Sandbox")
    owner = models.ForeignKey(User)
    weekday = models.CharField(
        max_length=15,
        choices = make_choice([
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ]))
    quadrant = models.CharField(
        max_length=1,
        choices = make_choice([
            "1", "2", "3", "4"]))
    value = models.CharField(
            blank=True,
            max_length=15,
            choices = make_choice([
                "Preparation",
                "Communication",
                "Meeting",]))

class QuadrantTime(models.Model):
    '''Represents the time of day covered by a specific quadrant id. Each user
    has four of these, one for each quadrant
    '''
    def __unicode__(self):
        return self.owner.get_full_name()

    objects = PursuitsManager()

    sandbox = models.ForeignKey("general.Sandbox")
    owner = models.ForeignKey(User)
    quadrant = models.CharField(
        max_length=1,
        choices = make_choice([
            "1", "2", "3", "4"]))
    start_time = models.TimeField()
    end_time = models.TimeField()
