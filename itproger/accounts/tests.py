from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class AuthenticationSmokeTests(SimpleTestCase):
    def test_login_page_is_available(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'accounts/login.html')

    def test_unknown_page_uses_custom_404(self):
        response = self.client.get('/this-page-does-not-exist/')

        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, 'front/404.html')


class LoginRedirectTests(TestCase):
    def test_successful_login_redirects_to_network_map(self):
        user = get_user_model().objects.create_user(
            username='map-user',
            password='test-password',
        )

        response = self.client.post(
            reverse('login'),
            {'username': user.username, 'password': 'test-password'},
        )

        self.assertRedirects(response, reverse('service'), fetch_redirect_response=False)
