from __future__ import annotations


def copy_fields(target: object, source: object, fields: tuple[str, ...]) -> None:
    for field in fields:
        setattr(target, field, getattr(source, field))


__all__ = ["copy_fields"]
