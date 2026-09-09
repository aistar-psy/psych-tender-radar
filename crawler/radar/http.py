"""Use the OS certificate store without disabling HTTPS verification."""
import ssl
import requests


class SystemTrustAdapter(requests.adapters.HTTPAdapter):
    def __init__(self, *args, **kwargs):
        try:
            import truststore
            self.tls_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        except ImportError:
            self.tls_context = ssl.create_default_context()
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = self.tls_context
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, proxy, **kwargs):
        kwargs['ssl_context'] = self.tls_context
        return super().proxy_manager_for(proxy, **kwargs)

    def build_connection_pool_key_attributes(self, request, verify, cert=None):
        host, kwargs = super().build_connection_pool_key_attributes(request, verify, cert)
        if verify is True:
            kwargs['ssl_context'] = self.tls_context
        return host, kwargs


def secure_session():
    session = requests.Session()
    session.mount('https://', SystemTrustAdapter())
    return session
