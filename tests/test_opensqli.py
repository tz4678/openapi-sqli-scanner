from opensqli.cli import _parse_args


def test_cli_args():
    args = _parse_args(
        [
            'https://fakeapi.com/v1/swagger.json',
            '--header',
            'Authorization: Bearer token',
        ]
    )
    print(args)
