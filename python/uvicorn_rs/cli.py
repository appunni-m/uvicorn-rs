"""Command-line entry point."""

import importlib


class ImportFromStringError(Exception):
    """An application import string could not be resolved."""


def _load_app(import_string):
    if not isinstance(import_string, str):
        return import_string
    module_name, separator, attrs = import_string.partition(":")
    if not module_name or not separator or not attrs:
        raise ImportFromStringError(
            f'Import string "{import_string}" must be in format "<module>:<attribute>".'
        )
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        raise ImportFromStringError(
            f'Could not import module "{module_name}".'
        ) from None
    instance = module
    try:
        for attr in attrs.split("."):
            instance = getattr(instance, attr)
    except AttributeError:
        raise ImportFromStringError(
            f'Attribute "{attrs}" not found in module "{module_name}".'
        ) from None
    return instance


def main(argv=None, prog="uvicorn-rs-py"):
    """Run the Uvicorn-compatible Click command under the distribution name."""
    from uvicorn.main import main as uvicorn_main

    uvicorn_main.main(args=argv, prog_name=prog, standalone_mode=True)


if __name__ == "__main__":
    main()
