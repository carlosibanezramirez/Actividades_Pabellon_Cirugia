from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.utils import timezone
from urllib.parse import urlencode
from secrets import choice as choose_available_room
from .forms import AgendaDateForm, ContinuousReservationForm, CorrectionForm, DashboardFilterForm, InterventionForm, ReservationRequestForm, WeeklyAgendaForm, WeeklySummaryForm, RescheduleReservationForm, CancelReservationForm, ReservationSearchForm
from .dashboard import STATES, event_statistics, room_board, room_snapshot, state_links
from .models import Event, Intervention, OperatingSettings, Reservation, Room, PreoperativeActivity
from .weekly_scheduling import continuous_day, reserve_continuous, week_start, reschedule_reservation, reservation_revision, cancel_reservation, find_available_rooms
from .scheduling import availability, reserve_hours
from .services import correct_event, create_intervention, record_event, complete_preoperative_activity
from .occupancy_summary import weekly_occupancy_summary, active_reservations_for_day
from .room_access import can_reserve_room
from .alarms import active_preparations, preparation_alarm


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@never_cache
def reservation_search(request):
    import secrets
    form = ReservationSearchForm(initial={'fecha': timezone.localdate()})
    context = {'form': form}
    if request.method == 'GET' and request.GET.get('confirmada'):
        try:
            booking_id = int(request.GET['confirmada'])
        except (ValueError, TypeError):
            raise Http404('Reserva no válida')
        booking = get_object_or_404(Reservation.objects.select_related('room', 'doctor', 'procedure'),
                                    pk=booking_id, created_by=request.user)
        context.update(saved=True, selected_room=booking.room, booking=booking,
                       details={'doctor': booking.doctor, 'patient_name': booking.patient_name,
                                'patient_rut': booking.patient_rut, 'diagnosis': booking.diagnosis,
                                'procedure': booking.procedure, 'duration_minutes': booking.planned_duration_minutes},
                       result={'planned': booking.planned_start_at, 'start': booking.starts_at,
                               'end': booking.ends_at, 'preparation_minutes': booking.preparation_minutes})
        return render(request, 'theatre/reservation_search.html', context)
    searches = request.session.get('reservation_searches', {})
    now = timezone.now().timestamp()
    searches = {key: value for key, value in searches.items() if value['expires'] > now}
    action = request.POST.get('action')
    if request.method == 'POST':
        if action == 'search':
            form = ReservationSearchForm(request.POST)
        else:
            pending = searches.get(request.POST.get('token', ''))
            if pending is None:
                messages.error(request, 'La búsqueda expiró o ya fue confirmada. Vuelva a buscar disponibilidad.')
                return redirect('reservation_search')
            form = ReservationSearchForm(pending['data'])
        context['form'] = form
        if form.is_valid():
            data = form.cleaned_data
            try:
                result = find_available_rooms(day=data['fecha'], desired_time=data['desired_time'],
                                              duration_minutes=data['duration_minutes'])
                if action == 'search':
                    if not result['rooms']:
                        context.update(searched=True)
                    else:
                        room = choose_available_room(result['rooms'])
                        token = secrets.token_urlsafe(24)
                        payload = {key: str(request.POST[key]) for key in form.fields}
                        searches = dict(list(searches.items())[-4:])
                        searches[token] = {'data': payload, 'expires': now + 900, 'room': room.pk,
                                           'preparation_minutes': result['preparation_minutes']}
                        context.update(result=result, token=token, selected_room=room, confirmation=True)
                elif action == 'confirm':
                    token = request.POST['token']
                    room = next((room for room in result['rooms'] if room.pk == pending.get('room')), None)
                    if room is None:
                        searches.pop(token, None)
                        form.add_error(None, 'El pabellón asignado ya no está disponible. Busque nuevamente para obtener otra asignación.')
                    elif pending.get('preparation_minutes') != result['preparation_minutes']:
                        searches[token]['preparation_minutes'] = result['preparation_minutes']
                        context.update(result=result, token=token, selected_room=room, confirmation=True)
                        form.add_error(None, 'El tiempo de preparación cambió. Revise el horario y confirme nuevamente.')
                    else:
                        booking = reserve_continuous(user=request.user, room=room, day=data['fecha'],
                            desired_time=data['desired_time'], duration_minutes=data['duration_minutes'],
                            doctor=data['doctor'], procedure=data['procedure'], patient_name=data['patient_name'],
                            patient_rut=data['patient_rut'], diagnosis=data['diagnosis'],
                            expected_preparation_minutes=pending['preparation_minutes'], automatic=True)
                        searches.pop(token, None)
                        request.session['reservation_searches'] = searches
                        messages.success(request, 'Reserva confirmada y registrada correctamente.')
                        return redirect(reverse('reservation_search') + '?' + urlencode({'confirmada': booking.pk}))
                else:
                    form.add_error(None, 'Acción no válida. Busque disponibilidad para asignar un pabellón.')
            except ValidationError as error:
                form.add_error(None, error)
    request.session['reservation_searches'] = searches
    context['details'] = form.cleaned_data if form.is_bound else {}
    return render(request, 'theatre/reservation_search.html', context)


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@never_cache
def preparation_status(request):
    return JsonResponse(active_preparations())


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
        policy = OperatingSettings.current()
        context.update({
            'room': room, 'monday': monday, 'sunday': monday + timedelta(days=6),
            'days': [continuous_day(room, monday + timedelta(days=i), policy=policy) for i in range(7)],
            'policy': policy,
            'previous_query': urlencode({'room': room.pk, 'fecha': (monday - timedelta(days=7)).isoformat()}),
            'next_query': urlencode({'room': room.pk, 'fecha': (monday + timedelta(days=7)).isoformat()}),
        })
    return render(request, 'theatre/weekly_agenda.html', context)


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@never_cache
def weekly_summary(request):
    from datetime import timedelta
    form = WeeklySummaryForm(request.GET if request.GET else {'fecha': timezone.localdate().isoformat()})
    context = {'form': form}
    if form.is_valid():
        monday = week_start(form.cleaned_data['fecha'])
        rows = weekly_occupancy_summary(monday)
        for row in rows:
            row['can_book'] = can_reserve_room(request.user, row['room'])
        context.update({
            'rooms': rows,
            'monday': monday, 'sunday': monday + timedelta(days=6),
            'previous_query': urlencode({'fecha': (monday - timedelta(days=7)).isoformat()}),
            'next_query': urlencode({'fecha': (monday + timedelta(days=7)).isoformat()}),
        })
    return render(request, 'theatre/weekly_summary.html', context)


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@never_cache
def day_reservations(request, room_id, day_string):
    from datetime import date
    room = get_object_or_404(Room, pk=room_id)
    try:
        day = date.fromisoformat(day_string)
        if not 1900 <= day.year <= 9997:
            raise ValueError
    except ValueError:
        raise Http404('Fecha no válida')
    return render(request, 'theatre/_day_reservations.html', {
        'room': room, 'day': day, 'bookings': active_reservations_for_day(room, day),
    })


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
            messages.success(request, f'Reserva #{booking.pk} confirmada: {start}–{end}, incluidos los {booking.preparation_minutes} minutos de preparación.')
            return redirect('weekly_day', room_id=room.pk, day_string=day.isoformat())
    return render(request, 'theatre/weekly_day.html', {
        'room': room, 'day': day_data, 'form': form,
        'day_link': reverse('weekly_day', args=[room.pk, day.isoformat()]),
        'has_starts': bool(allowed),
        'no_start_for_gap': request.GET.get('sin_inicio') == '1',
        'suggestion_expired': bool(suggested and suggested not in allowed),
        'week_query': urlencode({'room': room.pk, 'fecha': day.isoformat()}),
        'can_book': can_reserve_room(request.user, room) and day >= timezone.localdate(),
        'restricted_emergency': room.room_type == Room.Type.EMERGENCY and not can_reserve_room(request.user, room),
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
        'schedule': availability(day, user=request.user) if day else None,
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
        'can_start': not booking.cancelled_at and not hasattr(booking, 'intervention') and booking.starts_at <= timezone.now() < booking.ends_at,
    })


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@never_cache
def reservation_edit(request, pk):
    booking = get_object_or_404(Reservation.objects.select_related('room', 'procedure', 'doctor'), pk=pk)
    planned = timezone.localtime(booking.planned_start_at or booking.starts_at)
    initial = {'room': booking.room_id, 'fecha': planned.date(), 'desired_time': planned.strftime('%H:%M'),
               'revision': signing.dumps(reservation_revision(booking), salt='reservation-edit')}
    form = RescheduleReservationForm(request.POST if request.method == 'POST' else None, initial=initial, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            revision = signing.loads(form.cleaned_data['revision'], salt='reservation-edit')
            updated = reschedule_reservation(
                user=request.user, reservation_id=booking.pk, room=form.cleaned_data['room'],
                day=form.cleaned_data['fecha'], desired_time=form.cleaned_data['desired_time'],
                expected_revision=revision,
            )
        except signing.BadSignature:
            form.add_error(None, 'No se pudo validar la edición. Cierre el cuadro y vuelva a abrir la reserva.')
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Reserva actualizada correctamente.')
            return JsonResponse({'redirect_url': reverse('weekly_agenda') + '?' + urlencode({
                'room': updated.room_id,
                'fecha': timezone.localdate(updated.planned_start_at or updated.starts_at).isoformat(),
            })})
    return render(request, 'theatre/_reservation_edit_form.html', {
        'form': form, 'booking': booking,
        'cancel_form': CancelReservationForm(prefix='cancellation', initial={'revision': initial['revision']}),
    },
                  status=422 if request.method == 'POST' else 200)


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@require_POST
@never_cache
def reservation_cancel(request, pk):
    booking = get_object_or_404(Reservation.objects.select_related('room', 'doctor', 'procedure'), pk=pk)
    form = CancelReservationForm(request.POST, prefix='cancellation')
    if form.is_valid():
        try:
            revision = signing.loads(form.cleaned_data['revision'], salt='reservation-edit')
            updated = cancel_reservation(user=request.user, reservation_id=pk,
                                         reason=form.cleaned_data['reason'], expected_revision=revision)
        except signing.BadSignature:
            form.add_error(None, 'No se pudo validar la cancelación. Cierre el cuadro y vuelva a abrir la reserva.')
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, 'Reserva cancelada correctamente.')
            return JsonResponse({'redirect_url': reverse('weekly_agenda') + '?' + urlencode({
                'room': updated.room_id, 'fecha': timezone.localdate(updated.starts_at).isoformat(),
            })})
    planned = timezone.localtime(booking.planned_start_at or booking.starts_at)
    edit_form = RescheduleReservationForm(user=request.user, initial={
        'room': booking.room_id, 'fecha': planned.date(), 'desired_time': planned.strftime('%H:%M'),
        'revision': signing.dumps(reservation_revision(booking), salt='reservation-edit'),
    })
    return render(request, 'theatre/_reservation_edit_form.html', {
        'booking': booking, 'form': edit_form, 'cancel_form': form, 'cancellation_error': True,
    }, status=422)


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
def detail(request, pk, history=False):
    intervention = get_object_or_404(Intervention.objects.select_related('room', 'procedure', 'doctor', 'anesthetist', 'created_by', 'reservation'), pk=pk)
    events = list(intervention.events.select_related('recorded_by').prefetch_related('corrections__corrected_by'))
    by_stage = {e.stage: e for e in events}
    preoperative = {activity.kind: activity for activity in intervention.preoperative_activities.select_related('completed_by')}
    consents_complete = len(preoperative) == 2
    preoperative_rows = [{'kind': kind, 'label': label, 'activity': preoperative.get(kind),
                         'enabled': kind not in preoperative and not intervention.completed_at
                                    and not any(event.stage >= 3 for event in events)}
                        for kind, label in PreoperativeActivity.Kind.choices]
    rows = []
    previous = None
    for stage, label in Event.Stage.choices:
        event = by_stage.get(stage)
        elapsed = str(event.occurred_at - previous.occurred_at).split('.')[0] if event and previous else None
        rows.append({'stage': stage, 'label': label, 'event': event, 'enabled': stage == len(events) + 1 and not intervention.completed_at and (stage != 3 or consents_complete),
                     'blocked_consent': stage == 3 and len(events) == 2 and not consents_complete, 'elapsed': elapsed})
        if event:
            previous = event
    total = str(events[-1].occurred_at - events[0].occurred_at).split('.')[0] if len(events) == 9 else None
    policy = OperatingSettings.current()
    alarm = preparation_alarm(intervention.room_id, intervention.pk,
                              events[0].occurred_at if events else None,
                              events[-1].stage if events and not intervention.completed_at else None,
                              policy.preparation_max_minutes, timezone.now())
    return render(request, 'theatre/activity_history.html' if history else 'theatre/detail.html', {'intervention': intervention, 'rows': rows, 'count': len(events), 'total': total, 'alarm': alarm,
        'preoperative_rows': preoperative_rows, 'consent_count': len(preoperative)})


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
    return redirect(reverse('detail', args=[pk]) + '#pending-activities')


@login_required
@permission_required('theatre.operate_intervention', raise_exception=True)
@require_POST
def complete_preoperative(request, pk, kind):
    get_object_or_404(Intervention, pk=pk)
    try:
        complete_preoperative_activity(user=request.user, intervention_id=pk, kind=kind)
    except (ValidationError, IntegrityError) as error:
        messages.error(request, ' '.join(error.messages) if isinstance(error, ValidationError) else 'La actividad ya fue registrada.')
    else:
        messages.success(request, 'Actividad preoperatoria registrada con la fecha y hora del servidor.')
    return redirect(reverse('detail', args=[pk]) + '#pending-activities')


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
