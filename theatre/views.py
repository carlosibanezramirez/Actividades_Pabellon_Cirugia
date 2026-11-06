from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from urllib.parse import urlencode
from .forms import CorrectionForm, DashboardFilterForm, InterventionForm
from .dashboard import STATES, event_statistics, room_board, room_snapshot, state_links
from .models import Event, Intervention
from .services import correct_event, create_intervention, record_event


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
def board(request):
    return render(request, 'theatre/room_board.html', {
        'cards': room_board(), 'snapshot_at': timezone.now(),
    })


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
def dashboard(request):
    today = timezone.localdate()
    defaults = {'desde': today.replace(day=1).isoformat(), 'hasta': today.isoformat()}
    data = request.GET if ('desde' in request.GET or 'hasta' in request.GET) else defaults
    form = DashboardFilterForm(data)
    selected = request.GET.get('estado', '')
    if selected not in dict(STATES):
        selected = ''
    rooms, counts = room_snapshot()
    dates = defaults
    stats = None
    if form.is_valid():
        dates = {key: value.isoformat() for key, value in form.cleaned_data.items()}
        stats = event_statistics(form.cleaned_data['desde'], form.cleaned_data['hasta'])
    return render(request, 'theatre/dashboard.html', {
        'form': form, 'stats': stats, 'snapshot_at': timezone.now(),
        'total_rooms': len(rooms), 'cards': state_links(counts, dates, selected),
        'rooms': [row for row in rooms if not selected or row['state'] == selected],
        'selected': selected, 'selected_label': dict(STATES).get(selected, 'Todos los estados'),
        'all_query': urlencode(dates),
        'refresh_query': urlencode({**dates, **({'estado': selected} if selected else {})}),
    })


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
def interventions(request):
    queryset = Intervention.objects.select_related('room', 'procedure', 'doctor', 'anesthetist', 'created_by')
    status = request.GET.get('estado', 'curso')
    if status == 'finalizadas':
        queryset = queryset.filter(completed_at__isnull=False)
    elif status != 'todas':
        status = 'curso'
        queryset = queryset.filter(completed_at__isnull=True)
    return render(request, 'theatre/list.html', {'page': Paginator(queryset, 20).get_page(request.GET.get('page')), 'status': status})


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
def create(request):
    form = InterventionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            intervention = create_intervention(user=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        except IntegrityError:
            form.add_error(None, 'El pabellón ya tiene una intervención en curso.')
        else:
            return redirect('detail', pk=intervention.pk)
    return render(request, 'theatre/create.html', {'form': form})


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
def detail(request, pk):
    intervention = get_object_or_404(Intervention.objects.select_related('room', 'procedure', 'doctor', 'anesthetist', 'created_by'), pk=pk)
    events = list(intervention.events.select_related('recorded_by').prefetch_related('corrections__corrected_by'))
    by_stage = {e.stage: e for e in events}
    rows = []
    previous = None
    for stage, label in Event.Stage.choices:
        event = by_stage.get(stage)
        elapsed = str(event.occurred_at - previous.occurred_at).split('.')[0] if event and previous else None
        rows.append({'stage': stage, 'label': label, 'event': event, 'enabled': stage == len(events) + 1 and not intervention.completed_at, 'elapsed': elapsed})
        if event:
            previous = event
    total = str(events[-1].occurred_at - events[0].occurred_at).split('.')[0] if len(events) == 9 else None
    return render(request, 'theatre/detail.html', {'intervention': intervention, 'rows': rows, 'count': len(events), 'total': total})


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@require_POST
def record(request, pk, stage):
    get_object_or_404(Intervention, pk=pk)
    try:
        record_event(user=request.user, intervention_id=pk, stage=stage)
    except (ValidationError, IntegrityError) as exc:
        text = ' '.join(exc.messages) if isinstance(exc, ValidationError) else 'El evento ya fue registrado. Revise el estado actualizado.'
        messages.error(request, text)
    else:
        messages.success(request, 'Evento registrado con la hora del servidor.')
    return redirect('detail', pk=pk)


@login_required
@permission_required('theatre.correct_event', raise_exception=True)
def correct(request, pk, event_id):
    event = get_object_or_404(Event.objects.select_related('intervention'), pk=event_id, intervention_id=pk)
    form = CorrectionForm(request.POST or None, initial={'new_at': event.occurred_at, 'expected_at': event.occurred_at.isoformat()})
    if request.method == 'POST' and form.is_valid():
        try:
            correct_event(user=request.user, intervention_id=pk, event_id=event.pk, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Corrección guardada con historial de auditoría.')
            return redirect('detail', pk=pk)
    return render(request, 'theatre/correct.html', {'form': form, 'event': event})
