import unittest
from urllib.parse import urljoin

from urllib.request import urlopen
from urllib.error import HTTPError, URLError

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

try:
    from selenium import webdriver
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    webdriver = None

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    ChromeDriverManager = None

try:
    import webauthn
except ImportError:
    webauthn = None

from .utils import UserMixin


@unittest.skipUnless(webdriver, 'package selenium is not present')
@unittest.skipUnless(ChromeDriverManager, 'package webdriver-manager is not present')
@unittest.skipUnless(webauthn, 'package webauthn is not present')
class WebAuthnE2ETest(UserMixin, StaticLiveServerTestCase):
    port = 8000
    base_url = 'https://localhost'
    timeout = 8

    def assert_url(self, expected_url):
        assert self.webdriver.current_url == expected_url

    def setUp(self):
        self.login_url = urljoin(self.base_url, reverse("two_factor:login"))
        try:
            urlopen(self.login_url)
        except (URLError, HTTPError):
            return self.skipTest(f"server must be reachable at {self.login_url}")

        self.webdriver = webdriver.Chrome(ChromeDriverManager().install())

        super().setUp()
   
    def tearDown(self):
        self.webdriver.quit()
        super().tearDown()

    def setup_virtual_authenticator(self):
        self.webdriver.execute_cdp_cmd('WebAuthn.enable', {})
        virtual_authenticator_options = {
            'protocol' : 'u2f',
            'transport' : 'usb',
        }
        self.virtual_authenticator = self.webdriver.execute_cdp_cmd(
            'WebAuthn.addVirtualAuthenticator', {'options' : virtual_authenticator_options})
    
    def wait_for_element(self, selector_type, element):
        return WebDriverWait(self.webdriver, self.timeout).until(EC.presence_of_element_located((selector_type, element)))

    def wait_for_url(self, url):
        WebDriverWait(self.webdriver, self.timeout).until(EC.url_to_be(url))

    def do_login(self):
        self.wait_for_url(self.login_url)

        username = self.webdriver.find_element(By.ID, 'id_auth-username')
        username.clear()
        username.send_keys("bouke@example.com")

        password = self.webdriver.find_element(By.ID, 'id_auth-password')
        password.clear()
        password.send_keys("secret")

        button_next = self.webdriver.find_element(By.XPATH, "//button[@type='submit']")
        button_next.click()       

    def register_authenticator(self):
        self.wait_for_url(urljoin(self.base_url, reverse("two_factor:setup")))
        self.webdriver.find_element(By.XPATH, "//button[@type='submit']").click()

        self.wait_for_element(By.XPATH, "//input[@value='webauthn']").click()
        self.webdriver.find_element(By.XPATH, "//button[@class='btn btn-primary']").click()

    def test_webauthn_attestation_and_assertion(self):
        self.create_user()
        self.setup_virtual_authenticator()
        
        self.webdriver.get(self.login_url)
        self.do_login()

        # register the webauthn authenticator as a second factor
        self.wait_for_element(By.LINK_TEXT, "Enable Two-Factor Authentication").click()
        self.register_authenticator()
        self.wait_for_url(urljoin(self.base_url, reverse("two_factor:setup_complete")))

        # log out, log in
        self.webdriver.get(urljoin(self.base_url, reverse("logout") + '?next=' + reverse("two_factor:login")))
        self.do_login()

        # attempt to register the same authenticator, ending in failure
        self.wait_for_element(By.LINK_TEXT, "Add device").click()
        self.register_authenticator()
        self.wait_for_element(By.XPATH, "//p[@class='text-danger']")
