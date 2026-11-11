from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import OperatingSettings
from .start_times import start_times_for_day
from .tests import fixtures


class StartTimeTests(TestCase):
    def test_today_rounds_up_to_half_hour_with_preparation(self):
        now = timezone.make_aware(datetime(2027, 1, 12, 10, 10))
        self.assertEqual(start_times_for_day(now.date(), now)[0], '10:30')
        self.assertEqual(start_times_for_day(now.date(), now + timedelta(minutes=10))[0], '11:00')
        self.assertTrue(all(clock.endswith((':00', ':30')) for clock in start_times_for_day(now.date(), now)))

    def test_exact_boundary_midnight_and_future_day(self):
        now = timezone.make_aware(datetime(2027, 1, 12, 10, 15))
        self.assertEqual(start_times_for_day(now.date(), now)[0], '10:30')
        self.assertEqual(start_times_for_day(now.date() + timedelta(days=1), now)[0], '00:00')
        late = now.replace(hour=23, minute=50)
        self.assertEqual(start_times_for_day(late.date(), late), [])
        self.assertEqual(start_times_for_day(late.date() + timedelta(days=1), late)[0], '00:30')
        self.assertEqual(start_times_for_day(now.date() - timedelta(days=1), now), [])

    def test_configured_preparation_and_authenticated_api(self):
        user, _, _ = fixtures()
        now = timezone.make_aware(datetime(2027, 1, 12, 10, 10))
        policy = OperatingSettings.current()
        policy.preparation_mean_minutes = 30
        policy.save()
        self.assertEqual(start_times_for_day(now.date(), now)[0], '11:00')
        url = reverse('reservation_start_times')
        self.assertEqual(self.client.get(url).status_code, 302)
        with patch('theatre.start_times.timezone.now', return_value=now):
            self.client.force_login(user)
            response = self.client.get(url, {'fecha': now.date().isoformat()})
            self.assertEqual(response.json()['times'][0], '11:00')
            form = self.client.get(reverse('reservation_search')).context['form']
            self.assertEqual(form.fields['desired_time'].widget.choices[1][0], '11:00')
        self.assertEqual(self.client.get(url, {'fecha': 'incorrecta'}).status_code, 400)
