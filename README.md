# replacements

There is a single class of interest in this project: `Replacer`.

It is an object for replacing strings with other strings in json-like objects.

The initializer takes a list of _assignments_, each of which is a dictionary containing a `name`, a `type`, and optionally `args` and `kwargs`.

There are currently 5 implemented types:
* `identity`: returns the argument passed to it.
* `localfile`: passes the `args` and `kwargs` to `open` and then reads the file object. The mode is always 'r'.
* `fsspec`: passes the `args` and `kwargs` to `fsspec.open`, opens that, and reads. The mode is always 'r'. Requires fsspec to be installed. fsspec has multiple protocols installed, e.g. http(s), (s)ftp and zip. This can also be used for data on S3, if s3fs is installed.
* `awssecret`: takes two arguments: `region_name` and `secret_id`. Uses boto to call secretsmanager, and returns the returned `SecretString`.
* `env`: takes two arguments: `name`, and optionally a `default` value. If the environment variable doesn't exist and no default value was passed, an AssertionError will be raised.

Example:

```python
Replacer([{
    "name": "name",
    "type": "identity",
    "args": ["World"]
}])("Hello, ${name}!")
```

returns "Hello, World!"

There can be dependencies between the assignments. They are resolved
linearly using the list order:

```python
Replacer([
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
])("${greeting}")
```

also returns "Hello, World!"
