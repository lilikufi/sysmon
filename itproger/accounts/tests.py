from django.test import SimpleTestCase
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
