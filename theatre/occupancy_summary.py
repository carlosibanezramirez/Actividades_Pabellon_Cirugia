"""Resumen de intervalos libres por pabellón, sin redondear a bloques horarios."""
from datetime import timedelta

from django.utils import timezone

from .models import Reservation, Room
from .operating import booking_window
from .scheduling import day_slots, occupancy
from .weekly_scheduling import week_start


MINIMUM_FREE_INTERVAL = timedelta(minutes=75)


def weekly_occupancy_summary(day, now=None):
    now = now or timezone.now()
    monday = week_start(day)
    rooms = [{'room': room, 'days': []} for room in Room.objects.order_by('name', 'pk')]
    for offset in range(7):
        date = monday + timedelta(days=offset)
        _, periods = occupancy(date, now, minimum_use=timedelta(0))
        by_room = {}
        for period in periods:
            by_room.setdefault(period['room_id'], []).append(period)
        for row in rooms:
            room = row['room']
            room_periods = by_room.get(room.pk, [])
            reservations = {p['reservation'].pk: p['reservation'] for p in room_periods if p['reservation']}
            active_count = sum(reservation_is_active(booking, now) for booking in reservations.values())
            opening, closing = booking_window(date, room)
            cursor = max(opening, now)
            intervals = sorted((max(cursor, p['start']), min(closing, p['end']))
                               for p in room_periods if p['start'] < closing and p['end'] > cursor)
            free = []
            if room.active and cursor < closing:
                for start, end in intervals:
                    if start > cursor:
                        free.append({'start': cursor, 'end': start})
                    cursor = max(cursor, end)
                if cursor < closing:
                    free.append({'start': cursor, 'end': closing})
            free = [interval for interval in free
                    if interval['end'] - interval['start'] >= MINIMUM_FREE_INTERVAL]
            for interval in free:
                interval['minutes'] = int((interval['end'] - interval['start']).total_seconds() // 60)
            row['days'].append({
                'date': date, 'active_count': active_count, 'intervals': free,
                'free_minutes': sum(interval['minutes'] for interval in free),
                'past': date < timezone.localdate(now),
            })
    return rooms


def reservation_is_active(booking, now):
    return booking.ends_at > now and (
        getattr(booking, 'intervention', None) is None or booking.intervention.completed_at is None
    )


def active_reservations_for_day(room, day, now=None):
    now = now or timezone.now()
    slots = day_slots(day)
    bookings = Reservation.objects.filter(
        room=room, starts_at__lt=slots[-1]['end'], ends_at__gt=slots[0]['start'],
    ).select_related('procedure', 'doctor', 'intervention').order_by('starts_at', 'pk')
    return [booking for booking in bookings if reservation_is_active(booking, now)]
