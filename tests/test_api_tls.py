import json
from pathlib import Path
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

    @patch('app.integrations.django_api.Path.is_file', return_value=False)
    def test_packaged_roots_are_loaded_without_missing_system_paths(self, _is_file):
        with patch('app.integrations.django_api.ssl.create_default_context') as create_context:
            with patch('app.integrations.django_api.certifi.where', return_value='ca-bundle.pem'):
                DjangoApiClient('https://example.invalid', 'test-token')
        create_context.assert_called_once_with(cafile='ca-bundle.pem')
        create_context.return_value.load_verify_locations.assert_not_called()

    def test_standalone_bundle_is_preferred_over_python_package_path(self):
        expected = str(Path(__file__).resolve().parents[1] / 'certifi' / 'cacert.pem')
        with patch('app.integrations.django_api.Path.is_file', return_value=True):
            with patch('app.integrations.django_api.ssl.create_default_context') as create_context:
                with patch('app.integrations.django_api.certifi.where') as certifi_where:
                    DjangoApiClient('https://example.invalid', 'test-token')
        create_context.assert_called_once_with(cafile=expected)
        certifi_where.assert_not_called()
