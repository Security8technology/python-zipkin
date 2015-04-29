import logging

from scribe import scribe
from thrift.transport import TTransport, TSocket
from thrift.protocol import TBinaryProtocol

from zipkin.util import base64_thrift_formatter


logger = logging.getLogger(__name__)

CONNECTION_RETRIES = [1, 10, 20, 50, 100, 200, 400, 1000]


class Client(object):

    host = None
    port = 9410
    _client = None
    _connection_attempts = 0

    @classmethod
    def configure(cls, settings, prefix):
        cls.host = settings.get(prefix + 'collector')
        if prefix + 'collector.port' in settings:
            cls.port = int(settings[prefix + 'collector.port'])

    @classmethod
    def get_connection(cls):
        if not cls._client:
            cls._connection_attempts += 1

            max_retries = CONNECTION_RETRIES[-1]
            if ((cls._connection_attempts > max_retries) and
                    not ((cls._connection_attempts % max_retries) == 0)):
                return
            if ((cls._connection_attempts < max_retries) and
                    (cls._connection_attempts not in CONNECTION_RETRIES)):
                return

            try:
                socket = TSocket.TSocket(host=cls.host, port=cls.port)
                transport = TTransport.TFramedTransport(socket)
                protocol = TBinaryProtocol.TBinaryProtocol(trans=transport,
                                                           strictRead=False,
                                                           strictWrite=False)
                cls._client = scribe.Client(protocol)
                transport.open()

                cls._connection_attempts = 0
            except TTransport.TTransportException:
                cls._client = None
                logger.error("Can't connect to zipkin collector %s:%d"
                             % (cls.host, cls.port))
            except Exception:
                cls._client = None
                logger.exception("Can't connect to zipkin collector %s:%d"
                                 % (cls.host, cls.port))
        return cls._client

    @classmethod
    def log(cls, trace):
        if not cls.host:
            logger.debug('Zipkin tracing is disabled')
            return
        client = cls.get_connection()
        if client:
            messages = [base64_thrift_formatter(t, t.annotations)
                        for t in trace.children()]
            log_entries = [scribe.LogEntry('zipkin', message)
                           for message in messages]

            try:
                client.Log(messages=log_entries)
            except EOFError:
                cls._client = None
                logger.error('EOFError while logging a trace on zipkin '
                             'collector %s:%d' % (cls.host, cls.port))
            except Exception:
                cls._client = None
                logger.exception('Unknown Exception while logging a trace on '
                                 'zipkin collector %s:%d' % (cls.host,
                                                             cls.port))
        else:
            logger.warn("Can't log zipkin trace, not connected")


def log(trace):
    Client.log(trace)
