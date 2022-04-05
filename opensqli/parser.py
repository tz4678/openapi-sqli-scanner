import cgi
import copy
import functools
import urllib.parse as urlparse
from logging import getLogger
from typing import Any, Optional

import requests
import yaml

from . import __package_name__
from .constants import USER_AGENT

logger = getLogger(__package_name__)


class SchemaLoader:
    """Кеширует загруженные схемы"""

    YAML_MIMES: list[str] = [
        'text/vnd.yaml',
        'application/yaml',
        'application/x-yaml',
        'text/x-yaml',
    ]

    YAML_EXTS: tuple[str, ...] = ('.yml', '.yaml')

    def __init__(self, session: Optional[requests.Session] = None):
        self._session = session or self._create_session()
        self._cache = {}

    def _create_session(self) -> requests.Session:
        s = requests.session()
        s.headers.update({'User-Agent': USER_AGENT})
        return s

    def load(self, schema_url: str) -> dict[str, Any]:
        if schema_url not in self._cache:
            r = self._session.get(schema_url)
            ct, _ = cgi.parse_header(r.headers.get('content-type', ''))
            if ct in self.YAML_MIMES or schema_url.endswith(self.YAML_EXTS):
                schema = yaml.safe_load(r.text)
            else:
                schema = r.json()
            self._cache[schema_url] = schema
        return self._cache[schema_url]

    __call__ = load


class BaseParser:
    pass


class SwaggerParser(BaseParser):
    ALLOWED_METHODS: set[str] = {
        'get',
        'head',
        'post',
        'put',
        'patch',
        'delete',
        'options',
        'trace',
    }

    # По идее тут параметр schema лишний, так как мы всегда можем через loader получить схему по URL
    def __init__(
        self, schema: dict[str, Any], schema_url: str, loader: SchemaLoader
    ):

        self._schema_url = schema_url
        self._load = loader
        # Оно работает только потому, что закешированная схема есть
        self._schema = self._normalize_schema(schema)

    def get_server_urls(self) -> list[str]:
        base_path = self._schema.get('basePath', '/')
        if host := self._schema.get('host'):
            return [
                f'{scheme}://{host}{base_path}'.rstrip('/')
                for scheme in self._schema['schemes']
            ]
        return [urlparse.urljoin(self._schema_url, base_path).rstrip('/')]

    def get_paths(self) -> list[str]:
        return list(self._schema['paths'].keys())

    def get_operations(self, path: str) -> list[str]:
        return list(
            set(self._schema['paths'][path].keys()) & self.ALLOWED_METHODS
        )

    def get_parameters(self, path: str, operation: str) -> list[dict[str, Any]]:
        path_object = self._schema['paths'][path]
        defaults = path_object.get('parameters', {})
        path_item = path_object[operation]
        params = path_item.get('parameters', {})
        params = self._override_parameters(defaults, params)
        return copy.deepcopy(params)

    def filter_parameters(
        self, path: str, operation: str, location: str
    ) -> list[dict[str, Any]]:
        return list(
            filter(
                lambda x: x['in'] == location,
                self.get_parameters(path, operation),
            )
        )

    get_path_parameters = functools.partialmethod(
        filter_parameters, location='path'
    )
    get_query_parameters = functools.partialmethod(
        filter_parameters, location='query'
    )
    get_header_parameters = functools.partialmethod(
        filter_parameters, location='header'
    )
    get_body_parameters = functools.partialmethod(
        filter_parameters, location='body'
    )
    get_formdata_parameters = functools.partialmethod(
        filter_parameters, location='formData'
    )

    def has_payload(self, path: str, operation: str) -> bool:
        parameters = self.get_parameters(path, operation)
        return any(lambda x: x['in'] in ('body', 'formData'), parameters)

    def has_formdata(self, path: str, operation: str) -> bool:
        parameters = self.get_parameters(path, operation)
        return any(lambda x: x['in'] == 'formData', parameters)

    def get_payload_mimes(self, path: str, operation: str) -> list[str]:
        # Принимаемые типы можно объявить в корне и переопределить в Operation
        consumes = self._schema.get('consumes', [])
        # копируем объекты во избежание их модификации
        return list(
            self._schema['paths'][path][operation].get('consumes', consumes)
        )

    def _override_parameters(
        self, defaults: list[dict[str, Any]], overrides: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        make_key = lambda x: (x.get('name'), x.get('in'))
        out = {make_key(v): v for v in defaults}
        for v in overrides:
            out[make_key(v)] = v
        return list(out.values())

    def _normalize_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        return self._dereference(schema)

    # Допусти, что $ref может быть в любом месте
    def _dereference(self, o: Any) -> Any:
        if isinstance(o, dict):
            rv = {}
            for k, v in o.items():
                if '$ref' == k:
                    rv.update(self._resolve_reference(v))
                    # $ref'ы могут содержать $ref'ы
                    # rv = self._dereference(rv)
                    # Все после $ref должно игнорироваться
                    break
                rv[k] = self._dereference(v)
            return rv
        if isinstance(o, list):
            return [self._dereference(i) for i in o]
        assert isinstance(o, (int, float, str, bool))
        return o

    def _resolve_reference(self, ref: str) -> Any:
        logger.debug('resolve reference %s', ref)
        schema_url, path = ref.split('#', 2)
        schema = self._load(urlparse.urljoin(self._schema_url, schema_url))
        rv = schema
        for key in path.split('/')[1:]:
            key = key.replace('~1', '/').replace('~0', '~')
            rv = rv[key]
        return rv


# https://api.data.amsterdam.nl/signals/swagger/openapi.yaml
class OpenApiParser(SwaggerParser):
    def get_server_urls(self) -> list[str]:
        servers = self._schema.get('servers', [])
        # Правильно ли?
        urls = [x['url'] for x in servers] if servers else ['/']
        return [urlparse.urljoin(self._schema_url, u).rstrip('/') for u in urls]

    get_cookie_parameters = functools.partialmethod(
        SwaggerParser.filter_parameters, location='cookie'
    )

    def get_request_body(
        self, path: str, operation: str, mime: None | str = None
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        rv = self._schema['paths'][path][operation].get('requestBody', {})
        if mime:
            rv = rv.get('content', {}).get(mime)
        return copy.deepcopy(rv)

    def get_payload_mimes(self, path: str, operation: str) -> list[str]:
        return list(
            self.get_request_body(path, operation).get('content', {}).keys()
        )

    def has_payload(self, path: str, operation: str) -> bool:
        return len(self.get_payload_mimes(path, operation)) > 0


# Примеры ссылок на спецификацию:
# - https://app.andfrankly.com/api/data/swagger.yml (2)
# - https://railgun.spatialcurrent.io/swagger.yml (2)
# - https://navigationservice.e-spirit.cloud/docs/api/swagger-files/swagger.yml (3)
# - https://api.weather.gov/openapi.json (3)
# - https://www.skylinesoft.com/KB_Resources/PM/WebHelp/API/openapi.json (3)
# - https://coda.io/apis/v1/openapi.json (3)
# - https://georg.nrm.se/api/swagger.json (2)
# - https://michael1011.at/git/michael1011/market-maker-bot/src/branch/feat/reserved-balance/src/proto/xudrpc.swagger.json (2)
def create_parser(schema_url: str) -> SwaggerParser | OpenApiParser:
    loader = SchemaLoader()
    schema = loader(schema_url)
    # TODO: уточнить как их различать
    if 'swagger' in schema:
        return SwaggerParser(schema, schema_url, loader)
    if 'openapi' in schema:
        return OpenApiParser(schema, schema_url, loader)
    raise ValueError()
