from app.core.errors import DomainError


def validated_changes(body, required):
    changes = {key: getattr(body, key) for key in body.model_fields_set}
    if any(changes.get(key) is None for key in required if key in changes):
        raise DomainError(422, "invalid_field")
    return changes


def input_values(body, *, exclude=()):
    """Use validated native values internally, before API date serializers."""
    return {key: getattr(body, key) for key in type(body).model_fields if key not in exclude}
