import re
from typing import List, Callable, Dict, TypedDict, Any


class FunctionArguments(TypedDict, total=False):
    args: List[Any]
    kwargs: Dict[str, Any]


class Assignment(FunctionArguments, total=True):
    name: str
    type: str


replace_pattern = re.compile(r"\${[A-z_][A-z0-9_]*}")


data_retrievers: Dict[str, Callable[..., str]] = {}


def retriever(func: Callable[..., str]):
    name = func.__name__
    assert name.startswith("retriever_")
    name = name[len("retriever_"):]
    assert name not in data_retrievers, "no duplicate retriever names!"
    data_retrievers[name] = func
    return func


@retriever
def retriever_identity(s: str) -> str:
    return s


@retriever
def retriever_localfile(*args, **kwargs):
    with open(*args, mode='r', **kwargs) as f:
        return f.read()


@retriever
def retriever_fsspec(*args, **kwargs):
    import fsspec
    with fsspec.open(*args, **kwargs, mode='r').open() as f:
        return f.read()


@retriever
def retriever_awssecret(region_name, secret_id):
    import boto3
    return (
        boto3.client("secretsmanager", region_name=region_name)
        .get_secret_value(SecretId=secret_id)
        ['SecretString']
    )


@retriever
def retriever_env(name):
    import os
    res = os.getenv(name)
    assert res is not None
    return res


class Replacer:
    def __init__(
        self,
        assignments: List[Assignment],
        allow_missing: bool=False
    ) -> None:
        """
        An object for replacing strings with other strings in json-like objects

        Assignments is a list of dictionaries, each containing a `name`, a
        `type`, and optionally `args`, `kwargs` and `default`.
        If `allow_missing` is `False` (default), and a string to be replaced
        has a "${name}" with no assignment to "name", a KeyError exception will
        be thrown.

        There are currently 5 implemented types:
            - identity: returns the argument passed to it.
            - localfile: passes the `args` and `kwargs` to `open` and then reads
                the file object. The mode is always 'r'.
            - fsspec: passes the `args` and `kwargs` to `fsspec.open`, opens
                that, and reads. The mode is always 'r'. Requires fsspec to be
                installed. fsspec has multiple protocols installed, e.g.
                http(s), (s)ftp and zip. This can also be used for data on S3,
                if s3fs is installed.
            - awssecret: takes two arguments: `region_name` and `secret_id`.
                Uses boto to call secretsmanager, and returns the returned
                `SecretString`.
            - env: takes a single `name` argument, and looks for this 
                environment variable. If the environment variable doesn't exist
                and no default value was passed, an AssertionError will be
                raised.

        Example:
            >>> Replacer([{
            ...     "name": "name",
            ...     "type": "identity",
            ...     "args": ["World"]
            ... }])("Hello, ${name}!")
            Hello, World!

        There can be dependencies between the assignments. They are resolved
        linearly using the list order:
            >>> Replacer([
            ...     {
            ...         "name": "name",
            ...         "type": "identity",
            ...         "args": ["World"]
            ...     },
            ...     {
            ...         "name": "greeting",
            ...         "type": "identity",
            ...         "args": ["Hello, ${name}!"]
            ...     }
            ... ])("${greeting}")
            Hello, World!
        """
        self.variables: Dict[str, str] = {}
        self.allow_missing = allow_missing

        for assignment in assignments:
            assignment = self.replace(assignment)
            variable = assignment['name']
            data_retriever = data_retrievers[assignment['type']]

            try:
                self.variables[variable] = data_retriever(
                    *assignment.get('args', []),
                    **assignment.get('kwargs', {})
                )
            except KeyboardInterrupt:
                raise
            except Exception as e:
                if "default" in assignment:
                    self.variables[variable] = assignment["default"]
                else:
                    raise

    def replace(self, s):
        if isinstance(s, dict):
            return {self.replace(k): self.replace(v) for k, v in s.items()}
        elif isinstance(s, (list, tuple)):
            return [self.replace(v) for v in s]
        elif not isinstance(s, str):
            return s

        names = set(n[2:-1] for n in re.findall(replace_pattern, s))
        
        for name in names:
            if self.allow_missing and name not in self.variables:
                continue
            s = s.replace(f"${{{name}}}", self.variables[name])

        return s

    __call__ = replace


tests: List[Callable[[], None]] = []


def test(func: Callable[[], None]) -> Callable[[], None]:
    tests.append(func)
    return func


def runtests():
    for test in tests:
        test()


@test
def test_empty():
    assert Replacer([])("hello") == "hello"


@test
def test_allow_missing():
    try:
        Replacer([])("${hello}")
    except KeyError:
        pass
    else:
        raise Exception("allow_missing incorrect behavior")

    assert Replacer([], allow_missing=True)("${hello}") == "${hello}"


@test
def test_identity_args():
    replacer = Replacer([{
        "name": "hello",
        "type": "identity",
        "args": ["world"]
    }])

    assert replacer("hello") == "hello"
    assert replacer("${hello}") == "world"


@test
def test_identity_kwargs():
    replacer = Replacer([{
        "name": "hello",
        "type": "identity",
        "kwargs": {"s": "world"}
    }])

    assert replacer("hello") == "hello"
    assert replacer("${hello}") == "world"


@test
def test_dependency():
    replacer = Replacer([
        {
            "name": "name",
            "type": "identity",
            "args": ["World"]
        },
        {
            "name": "greeting",
            "type": "identity",
            "args": ["Hello, ${name}!"]
        }
    ])

    assert replacer("${greeting}") == "Hello, World!"


@test
def test_localfile():
    import tempfile
    with tempfile.NamedTemporaryFile('w') as f:
        f.write("Hello, World!")
        f.flush()

        replacer = Replacer([
            {
                "name": "a",
                "type": "localfile",
                "args": [f.name]
            }
        ])

        assert replacer("${a}") == "Hello, World!"


@test
def test_fsspec():
    import tempfile
    with tempfile.NamedTemporaryFile('w') as f:
        f.write("Hello, World!")
        f.flush()

        replacer = Replacer([
            {
                "name": "a",
                "type": "fsspec",
                "args": [f.name]
            }
        ])

        assert replacer("${a}") == "Hello, World!"


@test
def test_fsspec_google():
    replacer = Replacer([
        {
            "name": "a",
            "type": "fsspec",
            "args": ["https://www.google.com"]
        }
    ])

    assert "google" in replacer("${a}")


@test
def test_default():
    replacer = Replacer([{
        "name": "name",
        "type": "localfile",
        "args": "/best/path/ever/yo",
        "default": "World"
    }])

    assert replacer("Hello, ${name}!") == "Hello, World!"


@test
def test_env():
    import os
    os.environ["shimi"] = "Hello"
    replacer = Replacer([
        {
            "name": "greeting",
            "type": "env",
            "args": ["shimi"]
        },
        {
            "name": "name",
            "type": "env",
            "args": ["noshimi"],
            "default": "World"
        }
    ])

    assert replacer("${greeting}, ${name}!") == "Hello, World!"


@test
def test_no_env():
    try:
        Replacer([
            {
                "name": "a",
                "type": "env",
                "args": ["noshimi"]
            }
        ])
    except AssertionError:
        pass
    else:
        raise Exception("missing env didn't raise")


if __name__ == "__main__":
    runtests()
