import calendar
import datetime

from django.views.generic.list_detail import object_list
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth.decorators import permission_required
from django.contrib import messages

import pursuits
from pursuits.printable_pages import PrintViewContext
from pursuits.todos.forms import TodoForm
from pursuits.general.generic_views import add_edit_object
from pursuits.general.dbviews import TodoView
from pursuits.general.forms import TwoDateForm
from pursuits.permissions import can_edit_todo
from pursuits.todos.models import (Todo, ClusterItem, QuadrantTime,
                                   fetch_todos_for_monthly_view)
from pursuits.defaults import (TodoError, TODO_SORT_TYPES, MONTHLY_VIEWS,
                               MONTHLY_DETAILED_VIEW)
from pursuits.utils import (month_bounds, date_or_today, is_admin,
            set_selected_tabitem, forbidden_response, sandbox_from_request,
            fetch_random_quotes, check_current_application)
from pursuits.general.charts import (OverdueTodosXMLBuilder,
            TodoAveragePerDayXMLBuilder, TodoAverageDurationXMLBuilder,
            TodoPrioritiesXMLBuilder, TodoTaskTypeXMLBuilder,
            TodoMilestoneXMLBuilder)
from pursuits.todos.search import (TodoSearch, AllTodosSearch,
        LimboTodoSearch, mark_private, TODO_COMPLEX_DB_SORTING,
        TeamProjectTodosSearch, DeletedTodoSearch, CompletedTodoSearch,
        DependencyTodoSearch)

MAX_TODOS_PER_DAY = 4
MAX_TODOS_ON_DASHBOARD = 6


#
# Forms and custom data
#

DEFAULT_QUADRANT_TIMES = {
        1: {'start_time':datetime.time(8, 0), 'end_time':datetime.time(10, 0)},
        2: {'start_time':datetime.time(10, 0), 'end_time':datetime.time(12, 0)},
        3: {'start_time':datetime.time(13, 0), 'end_time':datetime.time(15, 0)},
        4: {'start_time':datetime.time(15, 0), 'end_time':datetime.time(17, 0)},
        }

#
# Helpers
#


def is_valid_sorting_option(option):
    return option.replace('-', '') in TODO_SORT_TYPES


def _todo_list(request, username=None, sort_by=None, title='',
               show_unassigned=None, engine_class=None, date=None,
               help_template=None, template=None,
               custom_filter_template=None, save_sort_pref=True):
    """Flat list of active todos that allow certain
    things to be edited inline.
    """
    if not is_admin(request.user) and username is None:
        username = request.user.username

    profile = request.user.get_profile()
    if username is not None:
        if request.user.has_perm("todos.edit_any_todo"):
            if username == "All":
                user = None
            else:
                user = get_object_or_404(User, username=username)
                sandbox = sandbox_from_request(request)
                if not user.get_profile().can_access_sandbox(sandbox):
                    return forbidden_response(request)
        else:
            user = request.user
    else:
        if is_admin(request.user) and profile.todolist_owner_dropdown:
            try:
                user = User.objects.get(
                                    username=profile.todolist_owner_dropdown)
            except User.DoesNotExist:
                user = None
        else:
            user = None

    profile.todolist_owner_dropdown = user.username if user else None
    profile.save()

    if not title:
        if not date or date == datetime.date.today():
            title = "To-Do Today"
        else:
            title = u"To-Dos on %s" % date.strftime("%A %B %d, %Y")
        if user:
            title = u"%s for %s" % (title,
                    user.get_profile().get_fullname())

    profile = request.user.get_profile()
    if sort_by is None:
        sort_by = (profile.last_todo_sorting or 'priority')

    sorting_rules = TODO_COMPLEX_DB_SORTING.get(
                                sort_by.replace('-', ''), False)
    if sorting_rules:
        if '-' in sort_by:
            default_order_by = [u"-%s" % op for op in sorting_rules]
        else:
            default_order_by = sorting_rules
    else:
        # this order by option is special and requires custom sorting
        # use the standard 'priority' for Django's order by
        default_order_by = 'priority'

    if save_sort_pref:
        # updating user preferences
        profile.last_todo_sorting = sort_by
        profile.save()
    
    if engine_class == None:
        engine_class = TodoSearch
    
    search_engine = engine_class(request, title=title, template=template,
            custom_filter_template=custom_filter_template, user=user,
            default_order_by=default_order_by, user_selected_order_by=sort_by,
            show_unassigned=show_unassigned, display_date=date,
            todo_help_template=help_template)
    
    if search_engine.show_unassigned == 'false':
        search_engine.show_unassigned = None

    return search_engine.render()


def _sorted_todo_list(request, method, sort_by=None, username=None, year=None,
        month=None, day=None, template=None, show_unassigned=None,
        custom_filter_template=None):

    if sort_by and not is_valid_sorting_option(sort_by):
        raise TodoError(u"Invalid sort field, got %s" % sort_by)

    if year:
        return method(request, username=username, sort_by=sort_by, year=year,
                show_unassigned=None,
                month=month, day=day, template=template,
                custom_filter_template=custom_filter_template)
    return method(request, username=username, sort_by=sort_by,
        show_unassigned=None,
        template=template, custom_filter_template=custom_filter_template)


def _todos_get_average_duration_per_day(todos):
    if not todos:
        return 0,0

    total_sec = 0
    # only count to-dos with duration
    todo_count = 0
    for todo in todos:
        if not todo.duration:
            continue

        todo_count += 1
        total_sec += todo.duration.hour * 60 * 60
        total_sec += todo.duration.minute * 60
        total_sec += todo.duration.second
    if not todo_count:
        return 0

    av = total_sec/todo_count
    return (av/ 3600.0), total_sec/3600.0


def _todos_average_get_per_day(todos):
    if not todos:
        return 0

    days_dict = {}
    for todo in todos:
        if todo.date:
            key = todo.date.strftime("%Y-%m-%d")
        else:
            key = datetime.date.today().strftime("%Y-%m-%d")
        if not days_dict.has_key(key):
            days_dict[key] = 0
        days_dict[key] += 1

    if not days_dict.keys():
        return 0
    return todos.count()/ len(days_dict.keys())


def _todos_get_percentage_overdue(todos, today, user):
    if not todos.count():
        return 0
    overdue = Todo.objects.filter(
            status__in=('Active', 'Limbo'),
            owner=user, date__lt=today).count()
    return overdue / float(todos.count()) * 100


#
# Views
#


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def todo_dashboard(request, username=None):
    agent = request.META.get("HTTP_USER_AGENT")
    if username:
        user = get_object_or_404(User, username=username)
        sandbox = sandbox_from_request(request)
        if not user.get_profile().can_access_sandbox(sandbox):
            return forbidden_response(request)
    else:
        user = request.user

    page_dict = {}
    sandbox = sandbox_from_request(request)
    today = datetime.date.today()

    # fetching to-do analysis
    alltodos = Todo.objects.filter(
            owner=user,
            status__in=("Active", "Limbo"))
    perc_overdue = _todos_get_percentage_overdue(alltodos, today, user)
    average_per_day = _todos_average_get_per_day(alltodos)
    average_duration, total_duration = _todos_get_average_duration_per_day(
                                                                alltodos)

    # only get completed to-dos created on the last 30 days
    my_all_todos = Todo.objects.filter(
            owner=user, status__in=("Active", "Limbo", "Completed")
            ).exclude(created_at__lt=today - datetime.timedelta(30),
                      status="Completed").order_by('-created_at', 'name')

    if 'iPad' not in agent:
        overdue_todos_xml = OverdueTodosXMLBuilder(perc_overdue).fetch_xml()
        average_per_day_xml = TodoAveragePerDayXMLBuilder(average_per_day,
                            alltodos.count(), user).fetch_xml()
        average_duration_xml = TodoAverageDurationXMLBuilder(average_duration,
                            total_duration, user).fetch_xml()
        todo_priority_xml = TodoPrioritiesXMLBuilder(my_all_todos).fetch_xml()
        todo_task_type_xml = TodoTaskTypeXMLBuilder(my_all_todos).fetch_xml()
        todo_milestones_xml = TodoMilestoneXMLBuilder(my_all_todos).fetch_xml()
    else:
        overdue_todos_xml = average_per_day_xml = average_duration_xml = ''
        todo_priority_xml = todo_task_type_xml =todo_milestones_xml = ''

    page_dict.update({
            'title': 'To-Do Dashboard',
            'agenda': Todo.objects.filter(owner=user,
                    time__isnull=False,
                    status="Active").order_by(
                    'date', 'time', 'name')[:MAX_TODOS_ON_DASHBOARD],

            'todos': Todo.objects.filter(owner=user,
                    time__isnull=True, status="Active",
                    priority__in=('Word', 'AA')).order_by(
                    'date', 'time', 'name')[:MAX_TODOS_ON_DASHBOARD],


            'latest_todos': Todo.objects.filter(owner=user,
                    status="Active").order_by(
                    '-created_at', 'name')[:MAX_TODOS_ON_DASHBOARD],

            'deleted_todos': Todo.objects.filter(deleted_by=user,
                    status="Inactive", cloned_from_deleted=True).order_by(
                    '-deleted_on', 'name')[:MAX_TODOS_ON_DASHBOARD],

            'average_per_day_xml': average_per_day_xml,
            'average_duration_xml': average_duration_xml,
            'overdue_todos_xml': overdue_todos_xml,

            'todo_priority_xml': todo_priority_xml,
            'todo_task_type_xml': todo_task_type_xml,
            'todo_milestones_xml': todo_milestones_xml,

            'selected_user': user,
            'quote': fetch_random_quotes(request),
            })

    if request.user.has_perm('todos.edit_any_todo'):
        page_dict["users"] = sandbox.all_users
    return render_to_response('todo_dashboard.html',
            PrintViewContext(request, page_dict))




@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def todo_list(request, year=None, month=None, day=None, username=None,
        sort_by=None, template=None, custom_filter_template=None,
        show_unassigned=None):
    """Flat list of active todos that allow certain
    things to be edited inline.
    """
    date = date_or_today(year, month, day)
    return _todo_list(request, username=username, sort_by=sort_by,
            date=date, help_template='help_todo_dayview.html',
            template=template,
            custom_filter_template=custom_filter_template,
            show_unassigned=show_unassigned)


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def todo_list_all(request, username=None, sort_by=None,
        show_unassigned=None, template=None, custom_filter_template=None):
    """List all todos"""
    set_selected_tabitem(request, 'nav_todos__list_all', 'nav_todos')
    return _todo_list(request, username=username, sort_by=sort_by,
            show_unassigned=show_unassigned,
            title="All To-Dos", engine_class=AllTodosSearch,
            help_template='help_todo_allview.html', template=template,
            custom_filter_template=custom_filter_template)


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def limbo_list(request, username=None, sort_by=None, show_unassigned=None,
               custom_filter_template=None, template=None):
    """List Limbo todos from that user"""
    return _todo_list(request, username=username, sort_by=sort_by,
            title="Limbo To-Dos", engine_class=LimboTodoSearch,
            show_unassigned=show_unassigned, template=template,
            custom_filter_template=custom_filter_template,
            help_template='help_todo_limboview.html')


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def completed_list(request, username=None, sort_by=None, show_unassigned=None,
               custom_filter_template=None, template=None,
               save_sort_pref=True):
    """List completed to-dos from that user"""
    profile = request.user.get_profile()
    if sort_by is None:
        sort_by = profile.last_completed_todo_sorting or None
    # Save user completed sort preference.
    if profile.last_completed_todo_sorting != sort_by:
        profile.last_completed_todo_sorting = sort_by
        profile.save()
    return _todo_list(request, username=username, sort_by=sort_by,
            title="Completed To-Dos", engine_class=CompletedTodoSearch,
            show_unassigned=show_unassigned, template=template,
            custom_filter_template=custom_filter_template,
            save_sort_pref=False)


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def deleted_list(request, username, sort_by=None, show_unassigned=None,
               custom_filter_template=None, template=None):
    if not is_admin(request.user):
        return forbidden_response(request)
    """List deleted todos from that user"""
    return _todo_list(request, username=username, sort_by=sort_by,
            title="Deleted To-Dos", engine_class=DeletedTodoSearch,
            show_unassigned=show_unassigned, template=template,
            custom_filter_template=custom_filter_template)


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def team_project_list(request, show_unassigned=None, username=None,
        sort_by=None, template=None, custom_filter_template=None):
    """Project todos """
    
    return _todo_list(request, username=username, sort_by=sort_by,
            title="Project To-Dos", template=template,
            custom_filter_template=custom_filter_template,
            engine_class=TeamProjectTodosSearch,
            show_unassigned=show_unassigned)

@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def dependency_list(request, todo_id):
    "Todos for a dependency graph."
    todo = get_object_or_404(Todo, pk=todo_id)
    graph_number = todo.dependency_graph_number()
    search_engine = DependencyTodoSearch(
        request, title="Dependency To-Dos",
        show_unassigned=True,
        graph_number=graph_number)
    return search_engine.render()


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def team_project_list_sort_by(request, sort_by, username=None):
    set_selected_tabitem(request,
                         'nav_groupprojects__todos',
                         'nav_groupprojects')
    return _sorted_todo_list(request, team_project_list, sort_by,
                             username=username)


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def todo_list_all_sort_by(request, sort_by, username=None,
                          template=None, custom_filter_template=None,
                          show_unassigned=None):
    return _sorted_todo_list(request, todo_list_all, sort_by,
                             username=username, template=template,
                             custom_filter_template=custom_filter_template,
                             show_unassigned=show_unassigned)


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def limbo_list_sort_by(request, sort_by, username=None, show_unassigned=None):
    return _sorted_todo_list(request, limbo_list, sort_by,
                username=username, show_unassigned=show_unassigned)


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def completed_list_sort_by(request, sort_by, username=None,
                           show_unassigned=None):
    return _sorted_todo_list(request, completed_list, sort_by,
                username=username, show_unassigned=show_unassigned)

@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def deleted_list_sort_by(request, sort_by, username=None,
                         show_unassigned=None):
    if not is_admin(request.user):
        return forbidden_response(request)
    return _sorted_todo_list(request, deleted_list, sort_by,
                username=username, show_unassigned=show_unassigned)


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def todo_list_sort_by(request, sort_by, year=None, month=None, day=None,
        username=None, template=None, custom_filter_template=None,
        show_unassigned=None):
    return _sorted_todo_list(request, todo_list, sort_by, username=username,
            year=year, month=month, day=day, template=template,
            custom_filter_template=custom_filter_template,
            show_unassigned=show_unassigned)


@can_edit_todo
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def edit_todo(request, todo_id):
    '''called when editing a todo. We can't use the generic view directly
    because we need to add some html for actions like postponing and
    delegating the todo'''

    todo = get_object_or_404(Todo, id=todo_id)
    page_dict = {}

    if todo.status == "Completed":
        page_dict = {"title": "View Completed To-Do",
                "noactions": True,
                "todo": TodoView.objects.get(id=todo_id)}
        return render_to_response("todo_view_completed.html",
                PrintViewContext(request, page_dict))

    return add_edit_object(request, model_form=TodoForm,
            object_id=todo_id, redirect_url="/todos/list/day/",
            title_type="To-Do",
            template_name="todo_edit_form.html", extra_context=page_dict,
            form_requires_request=True,
            extra_form_kwargs={'default_user': request.user.id})


@permission_required('todos.add_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def add_todo(request):
    """Called when adding a to-do."""
    return add_edit_object(request, model_form=TodoForm,
            redirect_url="/todos/list/day/", title_type="To-Do",
            template_name="todo_edit_form.html",
            form_requires_request=True,
            extra_form_kwargs={'default_user': request.user.id})


@can_edit_todo
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def view_todo(request, todo_id):
    '''Called when viewing a todo. This is similar to a todo list view except
    it only displays a single todo. This is used in places where it is
    necessary to view todo details AND action buttons including when viewing a
    todo clicked from the monthly todo list and when viewing a delegated
    todo.'''
    todo = get_object_or_404(TodoView, id=todo_id)
    search_results = [{"model": todo}]
    page_dict = {
            "title": u"View To-Do '%s'" % todo.name,
            "search_results": search_results,
            "num_hits": 1,
            "no_top_actions": True,
            "single_view_mode": True,
            }
    set_selected_tabitem(request, 'nav_todos__list_all', 'nav_todos')
    return render_to_response("todo_list.html", PrintViewContext(request,
        page_dict))


@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'), login_required=True)
def weekly(request, year=None, month=None, day=None, username=None):
    '''Display a weekly view of todos'''
    if username:
        if request.user.username == username or request.user.has_perm(
                'todos.edit_any_todo'): 
            user = get_object_or_404(User, username=username)
            sandbox = sandbox_from_request(request)
            if not user.get_profile().can_access_sandbox(sandbox):
                return forbidden_response(request)
        else:
            return forbidden_response(request)
    else:
        user = request.user

    date = date_or_today(year, month, day)
    weekdates = week_range(date)

    weekdays = []
    for weekday in weekdates:
        day = {}
        day["date"] = weekday
        day["dayname"] = weekday.strftime("%A")
        todos=TodoView.objects.filter(
            calendar_event=True,
            date=weekday,
            time__isnull=False,
            owner_id=user.id,
            status__in=("Active", 'Completed')).order_by('time')
        mark_private(request.user, todos)
        for todo in todos:
            tmodel = Todo.objects.get(id=todo.id)
            todo.show_unmonitor = request.user in tmodel.monitoring_users.all()
        day["todos"] = todos
        weekdays.append(day)
    page_dict = {
        "title": u"Meetings and Commitments for the week of %s" % (
        weekdates[0].strftime("%A %B %d, %Y")),
        "date": date,
        "today": datetime.date.today(),
        "weekdays": weekdays,
        "previous": u"/todos/weekly/%s" % (date-datetime.timedelta(7)).strftime(
                r"%Y/%m/%d"),
        "next": u"/todos/weekly/%s" % (date+datetime.timedelta(7)).strftime(
                r"%Y/%m/%d"),
        "current": u"/todos/weekly/%s" % (
            datetime.date.today().strftime("%Y/%m/%d")),
    }
    if request.user.has_perm("todos.edit_any_todo"):
        page_dict["todo_user"] = user
        page_dict['users'] = User.objects.all()
    return render_to_response('weekly.html', PrintViewContext(request, page_dict))


def get_view_mode_for_todo_monthly_page(request, profile):
    view_mode = request.GET.get('view_mode')
    if view_mode and view_mode not in MONTHLY_VIEWS.values():
        raise TodoError(u"Invalid view mode, got %s" % view_mode)

    view_mode = (view_mode or profile.todo_monthly_view_mode_str
                 or MONTHLY_VIEWS[MONTHLY_DETAILED_VIEW])

    # update profile settings
    profile.preferred_todo_monthly_view = [k
                    for k, v in MONTHLY_VIEWS.items() if v == view_mode][0]
    profile.save()
    return view_mode


@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'), login_required=True)
def monthly(request, year=None, month=None, day=1, username=None):
    '''Display a monthly view of todos.'''

    sandbox = sandbox_from_request(request)
    if username:
        if username == 'All':
            if not is_admin(request.user):
                return forbidden_response(request)
            user = None
        else:
            if request.user.username == username or request.user.has_perm(
                    'todos.edit_any_todo'):
                user = get_object_or_404(User,username=username)
                if not user.get_profile().can_access_sandbox(sandbox):
                    return forbidden_response(request)
            else:
                return forbidden_response(request)
    else:
        user = request.user

    profile = request.user.get_profile()
    view_mode = get_view_mode_for_todo_monthly_page(request, profile)

    date = date_or_today(year,month,day)
    monthstart, monthend = month_bounds(date)

    monthdays = fetch_todos_for_monthly_view(request, user, year, month, day)

    from pursuits3.utils import get_conf
    webcal_url = "webcal://%s.%s/crm/icalendar/feed" %(sandbox.url_base,get_conf('BASE_WEBSITE_URL'))

    page_dict = {
        "title": u"Meetings and Commitments for %s" % date.strftime("%B, %Y"),
        "date": date,
        "view_mode": view_mode,
        "today": datetime.date.today(),
        "weekheader": calendar.weekheader(10).split(),
        "monthdays": monthdays,
        "previous": u"/todos/monthly/%s" % (
                (monthstart-datetime.timedelta(1)).strftime("%Y/%m/%d")),
        "next": u"/todos/monthly/%s" % (
                (monthend+datetime.timedelta(1)).strftime("%Y/%m/%d")),
        "current": u"/todos/monthly/%s" % (
            datetime.date.today().strftime("%Y/%m/%d")),
        'webcal_url': webcal_url,
    }

    page_dict["todo_user"] = user
    if request.user.has_perm("todos.edit_any_todo"):
        # None means all users
        page_dict['users'] = [None] + list(sandbox.all_users)
    return render_to_response('monthly.html', PrintViewContext(
                                                request, page_dict))


@permission_required("todos.change_todo")
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def monitored_list(request):
    todos = request.user.monitored_todos.all()
    page_dict = {
        "title": "Monitored To-Dos",
    }
    return object_list(
        request,
        todos,
        template_name="monitored_todos.html",
        template_object_name="todo",
        allow_empty=True,
        extra_context=page_dict)


@permission_required('todos.change_todo')
@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'))
def bring_forward_all(request, username=None, prefix=''):
    if username:
        if request.user.username == username or request.user.has_perm(
                'todos.edit_any_todo'): 
            user = get_object_or_404(User, username=username)
            sandbox = sandbox_from_request(request)
            if not user.get_profile().can_access_sandbox(sandbox):
                return forbidden_response(request)
        else:
            return forbidden_response(request)
    else:
        user = request.user

    todos = Todo.objects.filter(owner=user, status="Active",
            time__isnull=True,
            date__lt=datetime.date.today())
    for t in todos:
        t.date = datetime.date.today()
        t.brought_forward += 1
        t.save()
    messages.success(request, 'Overdue todos brought forward')
    return HttpResponseRedirect(prefix + "/todos/list/day/")


@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'), login_required=True)
def task_clustering(request):
    '''Display the task Clustering report and timeline.'''
    sandbox = sandbox_from_request(request)

    user = request.user
    page_dict = {"title": u"Task Clustering for %s" % (
        user.get_profile().get_fullname())}
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday",
            "saturday", "sunday")
    quadrants = range(1,5)
    cluster_values = []

    if 'savecluster' in request.POST:
        for quadrant in quadrants:
            week = []
            for weekday in weekdays:
                cluster_value = ClusterItem.objects.get_or_create(owner=user,
                        sandbox=sandbox,
                        weekday=weekday, quadrant=unicode(quadrant))[0]
                cluster_value.value = request.POST[u'cluster_%s_%d' % (
                    weekday, quadrant)]
                cluster_value.save()
                week.append(cluster_value)
            cluster_values.append(week)
        messages.success(request, 'Cluster table saved')
    else:
        for quadrant in quadrants:
            week = []
            for weekday in weekdays:
                week.append(ClusterItem.objects.get_or_create(
                    sandbox=sandbox,
                    owner=user, weekday=weekday, quadrant=unicode(quadrant))[0])
            cluster_values.append(week)

    if 'savequadrants' in request.POST:
        quadrant_form = pursuits.todos.forms.QuadrantForm(request.POST)
        if quadrant_form.is_valid():
            quadrant_form.save(user)
            messages.success(request, 'Quadrant times saved')
    else:
        initial = {}
        for quadrant in quadrants:
            quadrant_time = QuadrantTime.objects.get_or_create(owner=user,
                    sandbox=sandbox,
                    quadrant=unicode(quadrant),
                    defaults=DEFAULT_QUADRANT_TIMES[quadrant])[0]
            initial[u"quadrant_%d_start" % quadrant] = quadrant_time.start_time
            initial[u"quadrant_%d_end" % quadrant] = quadrant_time.end_time
        quadrant_form = pursuits.todos.forms.QuadrantForm(initial)

    if 'generatereport' in request.POST:
        date_form = TwoDateForm(request.POST)
        if date_form.is_valid():
            start = date_form.cleaned_data['start_date']
            end = date_form.cleaned_data['end_date']
        else:
            start = end = None
    else:
        start = datetime.date.today()
        end = datetime.date.today()
        date_form = TwoDateForm(initial={
            "start_date": datetime.date.today(),
            "end_date": datetime.date.today()})

    if start:
        report = []
        # make it start on a monday
        start = start - datetime.timedelta(start.weekday())
        end = end + datetime.timedelta(7-end.weekday())

        delta = end - start
        week_report = []
        for date in (start + datetime.timedelta(i) for i in range(delta.days)):
            week_report.append((date, quadrant_report(user, date)))
            if date.weekday() == 6:
                report.append(week_report)
                week_report = []

        page_dict['week_reports'] = report


    page_dict.update(
        {"cluster_values": cluster_values,
        "weekdays": weekdays,
        "quadrant_form": quadrant_form,
        "date_form": date_form,
        })
    return render_to_response("task_clustering.html", PrintViewContext(
        request, page_dict))


def quadrant_report(user, date,
        category_retrieval_func=None):
    '''category_retrieval is a function that returns the category for a
    particular todo. This allows the function to do double duty for task
    clustering and task analysis'''
    if category_retrieval_func == None:
        category_retrieval_func = get_todo_category

    quadrants = range(1,5)
    todos = Todo.objects.filter(
            owner=user,
            status="Completed",
            date=date)
    report = {}
    for quadrant in quadrants:
        report[quadrant] = {
                "Preparation": 0,
                "Communication": 0,
                "Meeting": 0,
                }

    for todo in todos:
        category = category_retrieval_func(todo)
        quadrant = get_time_quadrant(user, todo)
        if not quadrant or not category:
            continue
        report[quadrant].setdefault(category, 0)
        report[quadrant][category] += (
                ((todo.duration and todo.duration.hour or 0) * 60) +
                (todo.duration and todo.duration.minute or 0))

    for quadrant in quadrants:
        # Being python 2.4 compliant is biting my ass
        #report[quadrant]['overall_category'] = max(report[quadrant],
                #key=lambda m: report[quadrant][m])
        report[quadrant]['overall_category'] = max(
                [(report[quadrant][m], m) for m in report[quadrant]])[1]
        if report[quadrant][report[quadrant]['overall_category']] == 0:
            report[quadrant]['overall_category'] = '-' 
        for task_type, duration in report[quadrant].items():
            if task_type == 'overall_category':
                continue
            hours = duration / 60
            minutes = duration % 60
            report[quadrant][task_type] = u"%s:%s" % (
                    unicode(hours).zfill(2),
                    unicode(minutes).zfill(2))

        goal = ClusterItem.objects.filter(
                weekday=date.strftime("%A").lower(),
                quadrant = unicode(quadrant),
                owner = user
                )
        if not goal or not goal[0].value:
            goal = '-'
        else:
            goal = goal[0].value
        report[quadrant]['goal_category'] = goal

        if goal == "-":
            report[quadrant]['colour'] = "#00f"
        elif goal == report[quadrant]['overall_category']:
            report[quadrant]['colour'] = "#0f0"
        else:
            report[quadrant]['colour'] = "#f00"
    return report


@check_current_application(('app_crm', 'app_compass', 'app_edp',
                            'app_meeting_manager'), login_required=True)
def anonymous_complete(request, anonymous_key):
    '''When a todo is delegated to an anonymous user, they can click a link
    that brings them to this view which will mark that todo as complete'''
    todo = get_object_or_404(Todo, anonymous_owner_key=anonymous_key)

    if request.POST:
        if "Yes" in request.POST:
            todo.status = "Completed"
            todo.save()
        else:
            return HttpResponseRedirect("/")

    page_dict = {
        "todo": todo,
    }

    if todo.status == "Completed":
        page_dict["message"] = \
                u"The todo titled '%s' has been marked %s. Thank you!" % (
                        todo.name, todo.status)
    else:
        page_dict["message"] = \
                u"Are you sure you want to mark \
                the todo titled '%s' as Completed?" % (
                        todo.name)
        page_dict["show_buttons"] = True
    return render_to_response('anonymous_complete.html',
          PrintViewContext(request, page_dict))


def week_range(date):
    '''Return a list of dates  containing the seven days of
    that contains the given date (starting at monday)'''
    weekstart = date - datetime.timedelta(date.weekday())
    return [weekstart + datetime.timedelta(x) for x in range(7)]


def get_todo_category(todo):
    # keep this import here to avoid circular import problems
    from pursuits.projects.views import get_scorecard_categories
    task_type = todo.task_type
    categories = get_scorecard_categories()
    category = categories.get(task_type)
    if task_type == "Drop-in Attempt":
        return "Meeting"
    elif category == "Preparation":
        return "Preparation"
    elif category == "Attempt" or category == "Contact":
        return "Communication"
    else: return "Meeting"


def get_time_quadrant(user, todo):
    '''return the time quadrant (1, 2, 3, 4) for the specific time for that
    user'''
    time = todo.time
    if time == None:
        time = datetime.time(todo.completed_at.hour, todo.completed_at.minute)

    quadrants = QuadrantTime.objects.filter(owner=user)
    for quadrant in quadrants:
        if quadrant.start_time <= time and quadrant.end_time >= time:
            return int(quadrant.quadrant)
    return None
