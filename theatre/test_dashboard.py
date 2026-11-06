from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .dashboard import duration_label, event_statistics, room_snapshot
from .models import Event, Intervention, Room
from .tests import fixtures


CHILE = ZoneInfo('America/Santiago')


class DashboardTests(TestCase):
    def setUp(self):
        self.user, self.administrator, self.intervention = fixtures()
        self.client.force_login(self.user)
        self.url = reverse('dashboard')

    def event(self, stage, at, intervention=None):
        return Event.objects.create(
            intervention=intervention or self.intervention, stage=stage,
            occurred_at=at, original_at=at, recorded_by=self.user,
        )

    def other_intervention(self, name):
        return Intervention.objects.create(
            room=Room.objects.create(name=name), procedure=self.intervention.procedure,
            doctor=self.intervention.doctor, anesthetist=self.intervention.anesthetist,
            created_by=self.user,
        )

    def test_current_states_and_preparation_procedure_exit_boundaries(self):
        free = Room.objects.create(name='Libre')
        unavailable = Room.objects.create(name='No disponible', active=False)
        rows, counts = room_snapshot()
        self.assertEqual(counts, {'libre': 1, 'preparacion': 1, 'procedimiento': 0, 'no_disponible': 1})
        for stage in range(1, 5):
            self.event(stage, timezone.now())
        self.assertEqual(room_snapshot()[1]['preparacion'], 1)
        self.event(5, timezone.now())
        self.assertEqual(room_snapshot()[1]['procedimiento'], 1)
        for stage in range(6, 10):
            self.event(stage, timezone.now())
        self.intervention.completed_at = timezone.now()
        self.intervention.save(update_fields=['completed_at'])
        self.assertEqual(room_snapshot()[1]['libre'], 2)
        self.assertEqual(sum(room_snapshot()[1].values()), Room.objects.count())

    def test_state_click_keeps_dates_and_filters_current_room_details(self):
        Room.objects.create(name='Libre para seleccionar')
        response = self.client.get(self.url, {'desde': '2020-01-01', 'hasta': '2020-01-31', 'estado': 'preparacion'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['room'].pk for row in response.context['rooms']], [self.intervention.room_id])
        self.assertEqual(response.context['selected_label'], 'En preparación')
        self.assertIn('desde=2020-01-01', response.context['cards'][0]['query'])
        self.assertEqual(response.context['stats']['event_count'], 0)
        self.assertContains(response, 'Sin eventos en las fechas seleccionadas')

    def test_calendar_is_inclusive_local_time_and_previous_event_can_be_outside_range(self):
        self.event(1, datetime(2026, 8, 9, 23, 55, tzinfo=CHILE))
        self.event(2, datetime(2026, 8, 10, 0, 5, tzinfo=CHILE))
        self.event(3, datetime(2026, 8, 10, 23, 59, 59, tzinfo=CHILE))
        self.event(4, datetime(2026, 8, 11, 0, 0, tzinfo=CHILE))
        stats = event_statistics(date(2026, 8, 10), date(2026, 8, 10))
        self.assertEqual(stats['event_count'], 2)
        self.assertEqual(stats['intervention_count'], 1)
        row = stats['rows'][1]
        self.assertEqual(row['events'], 1)
        self.assertEqual(row['samples'], 1)
        self.assertEqual(row['average'], '00:10:00')
        self.assertEqual(stats['rows'][0]['average'], '—')
        self.assertEqual(stats['rows'][3]['events'], 0)

    def test_average_minimum_maximum_zero_and_corrected_timestamps(self):
        start = datetime(2026, 8, 10, 10, tzinfo=CHILE)
        self.event(1, start)
        second = self.event(2, start + timedelta(minutes=10))
        another = self.other_intervention('Segundo pabellón')
        self.event(1, start, another)
        self.event(2, start + timedelta(minutes=20), another)
        stats = event_statistics(date(2026, 8, 10), date(2026, 8, 10))
        row = stats['rows'][1]
        self.assertEqual((row['samples'], row['average'], row['minimum'], row['maximum']),
                         (2, '00:15:00', '00:10:00', '00:20:00'))
        second.occurred_at = start
        second.save(update_fields=['occurred_at'])
        stats = event_statistics(date(2026, 8, 10), date(2026, 8, 10))
        self.assertEqual(stats['rows'][1]['minimum'], '00:00:00')
        self.assertEqual(stats['rows'][1]['average'], '00:10:00')
        self.assertEqual(second.original_at, start + timedelta(minutes=10))

    def test_incomplete_intervals_not_counted_as_zero_and_negative_intervals_excluded(self):
        start = datetime(2026, 8, 10, 10, tzinfo=CHILE)
        self.event(1, start)
        self.event(2, start - timedelta(minutes=1))
        self.event(4, start + timedelta(minutes=1))
        stats = event_statistics(date(2026, 8, 10), date(2026, 8, 10))
        self.assertEqual(stats['invalid_count'], 1)
        self.assertEqual(stats['rows'][1]['samples'], 0)
        self.assertEqual(stats['rows'][3]['samples'], 0)
        self.assertEqual(stats['rows'][3]['average'], '—')

    def test_unavailable_room_with_open_intervention_keeps_its_record(self):
        self.intervention.room.active = False
        self.intervention.room.save()
        rows, counts = room_snapshot()
        self.assertEqual(counts['no_disponible'], 1)
        self.assertEqual(rows[0]['intervention'].pk, self.intervention.pk)
        response = self.client.get(self.url, {'estado': 'no_disponible'})
        self.assertContains(response, reverse('detail', args=[self.intervention.pk]))

    def test_invalid_dates_show_errors_instead_of_statistics(self):
        for data in (
            {'desde': '2026-08-11', 'hasta': '2026-08-10'},
            {'desde': 'invalida', 'hasta': '2026-08-10'},
            {'desde': '2026-08-10'},
            {'desde': '2026-08-10', 'hasta': '9999-12-31'},
        ):
            with self.subTest(data=data):
                response = self.client.get(self.url, data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertIsNone(response.context['stats'])

    def test_access_control(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        user = get_user_model().objects.create_user(username='sin-acceso-panel')
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_duration_format_handles_more_than_one_day(self):
        self.assertEqual(duration_label(90061), '25:01:01')
        self.assertEqual(duration_label(None), '—')
