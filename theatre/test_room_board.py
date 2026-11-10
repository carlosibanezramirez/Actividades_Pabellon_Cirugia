from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .dashboard import room_board
from .models import Event, Intervention, Room
from .tests import fixtures


class RoomBoardTests(TestCase):
    def setUp(self):
        self.user, self.administrator, self.intervention = fixtures()
        self.client.force_login(self.user)
        self.url = reverse('room_board')

    def event(self, stage, at=None):
        at = at or timezone.now()
        return Event.objects.create(intervention=self.intervention, stage=stage,
                                    occurred_at=at, original_at=at, recorded_by=self.user)

    def finish(self):
        start = timezone.now() - timedelta(hours=2)
        for stage in range(1, 10):
            self.event(stage, start + timedelta(minutes=10 * (stage - 1)))
        self.intervention.completed_at = self.intervention.events.get(stage=9).occurred_at
        self.intervention.save(update_fields=['completed_at'])

    def test_rooms_without_history_show_availability_and_empty_details(self):
        Room.objects.create(name='Libre sin historial')
        Room.objects.create(name='Suspendido sin historial', active=False)
        cards = {card['room'].name: card for card in room_board()}
        self.assertEqual(cards['Libre sin historial']['state'], 'libre')
        self.assertIsNone(cards['Libre sin historial']['intervention'])
        self.assertEqual(cards['Suspendido sin historial']['state'], 'no_disponible')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sin intervenciones registradas', count=2)
        self.assertNotContains(response, 'Estadísticas de tiempos')

    def test_open_intervention_shows_preparation_then_procedure_and_details(self):
        self.event(1)
        card = room_board()[0]
        self.assertEqual(card['state'], 'preparacion')
        self.assertFalse(card['finished'])
        self.assertIsNotNone(card['intervention'].usage_started_at)
        self.assertIsNone(card['intervention'].usage_ended_at)
        response = self.client.get(self.url)
        self.assertContains(response, 'room-preparacion')
        self.assertContains(response, self.intervention.doctor.name)
        self.assertContains(response, self.intervention.procedure.name)
        self.assertContains(response, 'Pendiente')
        self.event(2)
        self.assertEqual(room_board()[0]['state'], 'procedimiento')

    def test_finalized_intervention_remains_visible_with_start_and_exit_times(self):
        self.finish()
        card = room_board()[0]
        self.assertEqual(card['state'], 'libre')
        self.assertTrue(card['finished'])
        self.assertEqual(card['intervention'].usage_started_at, self.intervention.events.get(stage=1).occurred_at)
        self.assertEqual(card['intervention'].usage_ended_at, self.intervention.events.get(stage=9).occurred_at)
        response = self.client.get(self.url)
        self.assertContains(response, '✓ Finalizada')
        self.assertContains(response, 'Ver última intervención')
        self.assertContains(response, self.intervention.procedure.name)

    def test_open_intervention_replaces_last_completed_one_even_if_its_creation_is_older(self):
        self.finish()
        new = Intervention.objects.create(
            room=self.intervention.room, procedure=self.intervention.procedure,
            doctor=self.intervention.doctor, anesthetist=self.intervention.anesthetist,
            created_by=self.user,
        )
        Intervention.objects.filter(pk=new.pk).update(created_at=self.intervention.created_at - timedelta(days=1))
        card = room_board()[0]
        self.assertEqual(card['intervention'].pk, new.pk)
        self.assertFalse(card['finished'])
        self.assertEqual(card['state'], 'no_disponible')

    def test_unavailable_room_keeps_completed_intervention_but_not_green_availability(self):
        self.finish()
        self.intervention.room.active = False
        self.intervention.room.save()
        card = room_board()[0]
        self.assertEqual(card['state'], 'no_disponible')
        self.assertTrue(card['finished'])
        self.assertEqual(card['state_reason'], 'Desactivado en Administración')

    def test_last_completed_intervention_is_selected_and_current_corrected_times_used(self):
        self.finish()
        last = Intervention.objects.create(
            room=self.intervention.room, procedure=self.intervention.procedure,
            doctor=self.intervention.doctor, created_by=self.user,
            completed_at=timezone.now(),
        )
        start, end = timezone.now() - timedelta(minutes=30), timezone.now()
        Intervention.objects.filter(pk=last.pk).update(created_at=self.intervention.created_at - timedelta(days=1))
        Event.objects.create(intervention=last, stage=1, occurred_at=start, original_at=start, recorded_by=self.user)
        Event.objects.create(intervention=last, stage=9, occurred_at=end, original_at=end - timedelta(minutes=2), recorded_by=self.user)
        with self.assertNumQueries(3):
            cards = room_board()
        self.assertEqual(cards[0]['intervention'].pk, last.pk)
        self.assertEqual(cards[0]['intervention'].usage_ended_at, end)

    def test_access_requires_login_and_permission(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        user = get_user_model().objects.create_user(username='sin-permiso-tablero')
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
