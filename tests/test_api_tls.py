import json
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from app.integrations.django_api import DjangoApiClient, DjangoApiError


class ApiTlsTests(unittest.TestCase):
    def test_requests_use_verified_context_with_hostname_checks(self):
        client = DjangoApiClient('https://example.invalid', 'test-token')
        response = Mock()
        response.read.return_value = json.dumps({'ok': True}).encode()
        with patch('app.integrations.django_api.urlopen') as open_url:
            open_url.return_value.__enter__.return_value = response
            self.assertTrue(client._request('GET', '/api/health')['ok'])
        context = open_url.call_args.kwargs['context']
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(context.cert_store_stats()['x509_ca'], 0)

    def test_certificate_failure_stops_request_without_insecure_retry(self):
        client = DjangoApiClient('https://example.invalid', 'test-token')
        with patch('app.integrations.django_api.urlopen', side_effect=URLError(
                ssl.SSLCertVerificationError(1, 'unable to get local issuer certificate'))) as open_url:
            with self.assertRaisesRegex(DjangoApiError, 'گواهی'):
                client._request('GET', '/api/health')
            self.assertEqual(open_url.call_count, 1)

    def test_system_trust_is_augmented_with_packaged_roots(self):
        with patch('app.integrations.django_api.ssl.create_default_context') as create_context:
            with patch('app.integrations.django_api.certifi.where', return_value='ca-bundle.pem'):
                DjangoApiClient('https://example.invalid', 'test-token')
        create_context.assert_called_once_with()
        create_context.return_value.load_verify_locations.assert_called_once_with(cafile='ca-bundle.pem')
