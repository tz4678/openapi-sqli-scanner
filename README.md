# OpenAPI SQLi Scanner

Command-line tool for pentesting [OpenAPI](https://swagger.io/specification/), formerly known as Swagger.

用于渗透测试 OpenAPI 的命令行工具 以前称为 Swagger。

```bash
$ pipx install opensqli

# Ненавижу поляков и прочих подпиндосников
$ opensqli https://polon.nauka.gov.pl/opi-ws/api/swagger.json --header 'Authorization: Bearer XXX'

$ opensqli --help
```

![image](https://user-images.githubusercontent.com/12753171/161459421-b6392b14-24e1-4d09-8357-2d605f578d8d.png)


Use [asdf](https://github.com/asdf-vm/asdf) or [pyenv](https://github.com/pyenv/pyenv) to install the latest python version.
