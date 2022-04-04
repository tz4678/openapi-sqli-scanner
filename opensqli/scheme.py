from typing import Any, Optional


def override_params(
    params: list[dict[str, Any]], overrides: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    # A list of parameters that are applicable for all the operations described
    # under this path. These parameters can be overridden at the operation
    # level, but cannot be removed there. The list MUST NOT include duplicated
    # parameters. A unique parameter is defined by a combination of a name and
    # location. The list can use the Reference Object to link to parameters that
    # are defined at the OpenAPI Object's components/parameters.
    make_key = lambda x: (x.get('name'), x.get('in'))
    output = {make_key(v): v for v in params}
    for v in overrides:
        output[make_key(v)] = v
    return list(output.values())


# navigationId:
#   name: navigationId
#   description: The id of the navigation.
#   in: path
#   required: true
#   schema:
#     $ref: '#/components/schemas/NavigationId'

# '#/components/schemas/NavigationId'.split('/')[1:]
# spec['components']['schemas']['NavigationId']

# components:
#   schemas:
#     NavigationId:
#       type: string
#       nullable: false

# $ref могут иметь:
# v2: Path Item Object, Schema Oject
# v3: components,
def resolve_reference(ref: str, schema: dict[str, Any]) -> Any:
    parts = ref.split('/')
    # ссылки могут быть и внешними
    assert parts[0] == '#', 'non local reference'
    rv = schema
    for key in parts[1:]:
        key = key.replace('~1', '/').replace('~0', '~')
        rv = rv[key]
    return rv


def normalize(
    o: Any,
    root: Optional[dict[str, Any]] = None,
    parent: Optional[dict[str, Any]] = None,
) -> Any:
    # FIXME: бесконечная рекурсия с кольцевыми ссылками
    root = root or o
    if isinstance(o, dict):
        rv = {}
        for k, v in o.items():
            # https://swagger.io/docs/specification/using-ref/
            if k == '$ref':
                # Ссылка может содержать ссылки
                rv.update(normalize(resolve_reference(k, root), root, o))
                # После $ref все игнорируется
                break
            # PathObject & PathItem parameters
            if (
                k == 'parameters'
                and parent is not None
                and parent.has('parameters')
            ):
                v = override_params(v, parent['parameters'])
            rv[k] = normalize(v, root, o)
        return rv
    if isinstance(o, list):
        return [normalize(v, root, parent) for v in o]
    # строки в python/js иммутабельны
    assert isinstance(o, (int, float, str, bool))
    return o
