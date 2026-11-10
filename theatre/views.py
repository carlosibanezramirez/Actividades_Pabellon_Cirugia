from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.utils import timezone
from urllib.parse import urlencode
from .forms import AgendaDateForm, ContinuousReservationForm, CorrectionForm, DashboardFilterForm, InterventionForm, ReservationRequestForm, WeeklyAgendaForm
from .dashboard import STATES, event_statistics, room_board, room_snapshot, state_links
from .models import Event, Intervention, Reservation, Room
from .weekly_scheduling import continuous_day, reserve_continuous, week_start
from .scheduling import availability, reserve_hours
from .services import correct_event, create_intervention, record_event


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@never_cache
def weekly_agenda(request):
    from datetime import timedelta
    initial_room = Room.objects.first()
    params = request.GET if request.GET else {
        'room': initial_room.pk if initial_room else '', 'fecha': timezone.localdate().isoformat(),
    }
    form = WeeklyAgendaForm(params)
    context = {'form': form}
    if form.is_valid():
        room = form.cleaned_data['room']
        monday = week_start(form.cleaned_data['fecha'])
        context.update({
            'room': room, 'monday': monday, 'sunday': monday + timedelta(days=6),
            'days': [continuous_day(room, monday + timedelta(days=i)) for i in range(7)],
            'previous_query': urlencode({'room': room.pk, 'fecha': (monday - timedelta(days=7)).isoformat()}),
            'next_query': urlencode({'room': room.pk, 'fecha': (monday + timedelta(days=7)).isoformat()}),
        })
    return render(request, 'theatre/weekly_agenda.html', context)


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@never_cache
def weekly_day(request, room_id, day_string):
    from datetime import date
    room = get_object_or_404(Room, pk=room_id)
    try:
        day = date.fromisoformat(day_string)
        if not 1900 <= day.year <= 9997:
            raise ValueError
    except ValueError:
        raise Http404('Fecha no válida')
    day_data = continuous_day(room, day)
    allowed = [option['value'] for option in day_data['start_options']]
    suggested = request.GET.get('inicio', '')
    initial = {'desired_time': suggested} if suggested in allowed else {}
    form = ContinuousReservationForm(request.POST or None, initial=initial, allowed_times=allowed)
    if request.method == 'POST' and form.is_valid():
        try:
            booking = reserve_continuous(user=request.user, room=room, day=day, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            start = timezone.localtime(booking.starts_at).strftime('%d/%m %H:%M')
            end = timezone.localtime(booking.ends_at).strftime('%d/%m %H:%M')
            messages.success(request, f'Reserva #{booking.pk} confirmada: {start}–{end}, incluidos los 15 minutos de preparación.')
            return redirect('weekly_day', room_id=room.pk, day_string=day.isoformat())
    return render(request, 'theatre/weekly_day.html', {
        'room': room, 'day': day_data, 'form': form,
        'day_link': reverse('weekly_day', args=[room.pk, day.isoformat()]),
        'has_starts': bool(allowed),
        'no_start_for_gap': request.GET.get('sin_inicio') == '1',
        'suggestion_expired': bool(suggested and suggested not in allowed),
        'week_query': urlencode({'room': room.pk, 'fecha': day.isoformat()}),
        'can_book': room.active and day >= timezone.localdate(),
    })


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
def board(request):
    return render(request, 'theatre/room_board.html', {
        'cards': room_board(), 'snapshot_at': timezone.now(),
    })


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@never_cache
def agenda(request):
    dates = request.POST if request.method == 'POST' else {'fecha': request.GET.get('fecha', timezone.localdate().isoformat())}
    date_form = AgendaDateForm(dates)
    day = date_form.cleaned_data['fecha'] if date_form.is_valid() else None
    form = ReservationRequestForm(request.POST or None, day=day)
    if request.method == 'POST' and day and form.is_valid():
        try:
            booking = reserve_hours(user=request.user, day=day, selections=form.cleaned_data['slots'],
                                    doctor=form.cleaned_data['doctor'], procedure=form.cleaned_data['procedure'],
                                    patient_name=form.cleaned_data['patient_name'], patient_rut=form.cleaned_data['patient_rut'])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f'Reserva #{booking.pk} registrada correctamente.')
            return redirect('reservation_detail', pk=booking.pk)
    return render(request, 'theatre/agenda.html', {
        'date_form': date_form, 'form': form, 'day': day,
        'schedule': availability(day) if day else None,
        'selected_slots': request.POST.getlist('slots') if request.method == 'POST' else [],
        'snapshot_at': timezone.now(),
    })


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@never_cache
def reservation_detail(request, pk):
    booking = get_object_or_404(Reservation.objects.select_related('room', 'doctor', 'procedure', 'created_by', 'intervention'), pk=pk)
    return render(request, 'theatre/reservation_detail.html', {
        'booking': booking,
        'can_start': not hasattr(booking, 'intervention') and booking.starts_at <= timezone.now() < booking.ends_at,
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
    initial = {}
    booking = None
    if request.method == 'GET' and request.GET.get('reserva'):
        try:
            booking = get_object_or_404(Reservation, pk=int(request.GET['reserva']))
        except (TypeError, ValueError):
            raise Http404('Reserva no encontrada')
        initial = {'room': booking.room_id, 'doctor': booking.doctor_id,
                   'procedure': booking.procedure_id, 'reservation': booking.pk}
    form = InterventionForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            intervention = create_intervention(user=request.user, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        except IntegrityError:
            form.add_error(None, 'El pabellón ya tiene una intervención en curso.')
        else:
            return redirect('detail', pk=intervention.pk)
    return render(request, 'theatre/create.html', {'form': form, 'booking': booking})


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@never_cache
def detail(request, pk):
    intervention = get_object_or_404(Intervention.objects.select_related('room', 'procedure', 'doctor', 'anesthetist', 'created_by', 'reservation'), pk=pk)
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
