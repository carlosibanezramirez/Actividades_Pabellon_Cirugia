from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Reservation, Room
from .occupancy_summary import weekly_occupancy_summary
from .tests import fixtures
from .weekly_scheduling import week_start


class WeeklyOccupancySummaryTests(TestCase):
    def setUp(self):
        self.user, self.administrator, self.item = fixtures()
        self.room = self.item.room
        self.monday = week_start(timezone.localdate()) + timedelta(days=7)
        self.client.force_login(self.user)

    def instant(self, clock, day=None):
        return timezone.make_aware(datetime.combine(day or self.monday, clock))

    def booking(self, start, end, day=None):
        return Reservation.objects.create(
            room=self.room, doctor=self.item.doctor, procedure=self.item.procedure,
            patient_name='Paciente ficticio resumen', patient_rut='12345678-5',
            starts_at=self.instant(start, day), ends_at=self.instant(end, day), created_by=self.user,
        )

    def test_exact_gaps_minutes_active_count_and_all_seven_days(self):
        self.booking(time(7), time(12, 40))
        self.booking(time(16, 30), time(18, 50))
        self.booking(time(21), time(23))
        rows = weekly_occupancy_summary(self.monday + timedelta(days=2))
        self.assertEqual(len(rows[0]['days']), 7)
        day = rows[0]['days'][0]
        self.assertEqual(day['date'], self.monday)
        self.assertEqual(day['active_count'], 3)
        self.assertEqual(day['free_minutes'], 360)
        self.assertEqual([(timezone.localtime(i['start']).time(), timezone.localtime(i['end']).time(), i['minutes'])
                          for i in day['intervals']], [(time(12, 40), time(16, 30), 230),
                                                       (time(18, 50), time(21), 130)])
        response = self.client.get(reverse('weekly_summary'), {'fecha': self.monday.isoformat()})
        self.assertContains(response, '12:40 – 16:30')
        self.assertContains(response, '230 minutos disponibles')
        self.assertContains(response, '18:50 – 21:00')
        self.assertContains(response, '130 minutos disponibles')
        self.assertContains(response, '3 reservas activas')
        self.assertNotContains(response, 'Paciente ficticio resumen')

    def test_gaps_below_75_minutes_are_hidden_and_excluded_from_total(self):
        self.booking(time(7), time(12))
        self.booking(time(13, 14), time(15))
        self.booking(time(16, 15), time(23))
        day = weekly_occupancy_summary(self.monday)[0]['days'][0]
        self.assertEqual(day['active_count'], 3)
        self.assertEqual([gap['minutes'] for gap in day['intervals']], [75])
        self.assertEqual(day['free_minutes'], 75)
        response = self.client.get(reverse('weekly_summary'), {'fecha': self.monday.isoformat()})
        self.assertNotContains(response, '12:00 – 13:14')
        self.assertContains(response, '15:00 – 16:15')
        self.assertContains(response, '75 minutos disponibles')
        self.assertContains(response, '<th scope="col">', count=7)

    def test_room_hours_inactive_rooms_and_empty_days(self):
        other = Room.objects.create(name='Otro pabellón', opening_time=time(9), closing_time=time(18))
        closed = Room.objects.create(name='Pabellón inactivo', active=False)
        rows = {row['room'].pk: row['days'][0] for row in weekly_occupancy_summary(self.monday)}
        self.assertEqual(rows[self.room.pk]['free_minutes'], 960)
        self.assertEqual(rows[other.pk]['free_minutes'], 540)
        self.assertEqual(rows[other.pk]['active_count'], 0)
        self.assertEqual(rows[closed.pk]['intervals'], [])
        response = self.client.get(reverse('weekly_summary'), {'fecha': self.monday.isoformat()})
        self.assertContains(response, 'class="card occupancy-day', count=21)
        self.assertContains(response, 'Pabellón no disponible.')

    def test_overnight_booking_counts_and_blocks_following_week(self):
        self.room.opening_time = time(0)
        self.room.save()
        Reservation.objects.create(
            room=self.room, doctor=self.item.doctor, procedure=self.item.procedure,
            patient_name='Paciente ficticio nocturno', starts_at=self.instant(time(22, 45), self.monday - timedelta(days=1)),
            planned_start_at=self.instant(time(23), self.monday - timedelta(days=1)),
            ends_at=self.instant(time(2)), created_by=self.user,
        )
        day = weekly_occupancy_summary(self.monday)[0]['days'][0]
        self.assertEqual(day['active_count'], 1)
        self.assertEqual(timezone.localtime(day['intervals'][0]['start']).time(), time(2))
        self.assertEqual(day['free_minutes'], 21 * 60)

    def test_preparation_is_occupied_and_overlapping_actual_use_is_not_counted_twice(self):
        booking = self.booking(time(9, 15), time(11))
        booking.planned_start_at = self.instant(time(9, 30))
        booking.save()
        self.item.reservation = booking
        self.item.created_at = self.instant(time(9, 15))
        self.item.completed_at = self.instant(time(11, 30))
        self.item.save()
        now = self.instant(time(8))
        day = weekly_occupancy_summary(self.monday, now=now)[0]['days'][0]
        self.assertEqual(day['active_count'], 0)  # Uso completado, no reserva activa.
        self.assertEqual([(timezone.localtime(i['start']).time(), timezone.localtime(i['end']).time())
                          for i in day['intervals']], [(time(8), time(9, 15)), (time(11, 30), time(23))])

    def test_past_dates_and_elapsed_minutes_are_not_offered(self):
        self.item.completed_at = timezone.now()
        self.item.save()
        now = self.instant(time(12, 40), self.monday + timedelta(days=2))
        days = weekly_occupancy_summary(self.monday, now=now)[0]['days']
        self.assertTrue(days[0]['past'])
        self.assertEqual(days[0]['intervals'], [])
        self.assertEqual(timezone.localtime(days[2]['intervals'][0]['start']).time(), time(12, 40))

    def test_authentication_permissions_invalid_date_and_no_rooms(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('weekly_summary')).status_code, 302)
        outsider = get_user_model().objects.create_user(username='sin-permisos')
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse('weekly_summary')).status_code, 403)
        self.client.force_login(self.user)
        for value in ['incorrecta', '9999-12-31', '1900-01-01-invalid']:
            response = self.client.get(reverse('weekly_summary'), {'fecha': value})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
        self.item.delete()
        self.room.delete()
        self.assertContains(self.client.get(reverse('weekly_summary')), 'No hay pabellones configurados.')
